"""Binary mask geometry and measurements (no Qt)."""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw


def empty_mask(height: int, width: int) -> np.ndarray:
    """Create an empty uint8 mask (0 background, 255 foreground)."""
    if height <= 0 or width <= 0:
        raise ValueError("height and width must be positive")
    return np.zeros((int(height), int(width)), dtype=np.uint8)


def mask_area_px(mask: np.ndarray | None) -> int:
    """Count foreground pixels (any non-zero)."""
    if mask is None or mask.size == 0:
        return 0
    return int(np.count_nonzero(mask))


def ensure_binary_mask(mask: np.ndarray) -> np.ndarray:
    """Return uint8 mask with values in {0, 255}."""
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)
    out = np.where(mask > 0, np.uint8(255), np.uint8(0)).astype(np.uint8)
    return np.ascontiguousarray(out)


def polygon_to_mask(
    points: Sequence[Sequence[float]],
    height: int,
    width: int,
    *,
    fill: int = 255,
) -> np.ndarray:
    """Rasterize a polygon into a binary mask (image pixel coordinates)."""
    mask = empty_mask(height, width)
    if len(points) < 3:
        return mask
    pts = [(float(p[0]), float(p[1])) for p in points]
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    draw.polygon(pts, outline=fill, fill=fill)
    arr = np.array(img, dtype=np.uint8)
    return ensure_binary_mask(arr)


def apply_disk_brush(
    mask: np.ndarray,
    x: float,
    y: float,
    radius: float,
    *,
    value: int = 255,
) -> np.ndarray:
    """Paint a filled disk onto mask (in-place friendly; returns same array)."""
    if radius <= 0:
        return mask
    h, w = mask.shape[:2]
    cx, cy = float(x), float(y)
    r = float(radius)
    x0 = max(int(np.floor(cx - r)), 0)
    x1 = min(int(np.ceil(cx + r)) + 1, w)
    y0 = max(int(np.floor(cy - r)), 0)
    y1 = min(int(np.ceil(cy + r)) + 1, h)
    if x0 >= x1 or y0 >= y1:
        return mask
    yy, xx = np.ogrid[y0:y1, x0:x1]
    disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    if value:
        mask[y0:y1, x0:x1][disk] = np.uint8(255)
    else:
        mask[y0:y1, x0:x1][disk] = np.uint8(0)
    return mask


def apply_brush_stroke(
    mask: np.ndarray,
    points: Sequence[Sequence[float]],
    radius: float,
    *,
    value: int = 255,
) -> np.ndarray:
    """Paint along a polyline of brush centers (interpolated for gaps)."""
    if not points:
        return mask
    if len(points) == 1:
        return apply_disk_brush(mask, points[0][0], points[0][1], radius, value=value)

    for i in range(len(points) - 1):
        x0, y0 = float(points[i][0]), float(points[i][1])
        x1, y1 = float(points[i + 1][0]), float(points[i + 1][1])
        dist = max(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5, 1e-6)
        step = max(radius * 0.35, 0.5)
        n = max(int(np.ceil(dist / step)), 1)
        for k in range(n + 1):
            t = k / n
            apply_disk_brush(
                mask,
                x0 + t * (x1 - x0),
                y0 + t * (y1 - y0),
                radius,
                value=value,
            )
    return mask


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return (x0, y0, x1, y1) exclusive max corner, or None if empty."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def point_in_mask(mask: np.ndarray, x: float, y: float) -> bool:
    """Test if integer pixel under (x,y) is foreground."""
    h, w = mask.shape[:2]
    ix, iy = int(np.floor(x)), int(np.floor(y))
    if ix < 0 or iy < 0 or ix >= w or iy >= h:
        return False
    return bool(mask[iy, ix])


def simplify_polyline(
    points: Sequence[Sequence[float]],
    *,
    max_points: int = 200,
) -> list[list[float]]:
    """Uniform subsample if too many points."""
    pts = [[float(p[0]), float(p[1])] for p in points]
    if len(pts) <= max_points or max_points < 3:
        return pts
    idx = np.linspace(0, len(pts) - 1, max_points).astype(int)
    return [pts[i] for i in idx]


def mask_to_contour(
    mask: np.ndarray,
    *,
    max_points: int = 200,
) -> list[list[float]]:
    """Extract an ordered exterior contour via Moore neighborhood tracing.

    Returns list of [x, y] in image coordinates. Empty list if mask empty.
    """
    binary = mask > 0
    if not np.any(binary):
        return []

    ys, xs = np.nonzero(binary)
    start_idx = int(np.argmin(ys * binary.shape[1] + xs))
    start = (int(xs[start_idx]), int(ys[start_idx]))

    neighbors = [
        (-1, 0),
        (-1, -1),
        (0, -1),
        (1, -1),
        (1, 0),
        (1, 1),
        (0, 1),
        (-1, 1),
    ]

    def is_fg(px: int, py: int) -> bool:
        h, w = binary.shape
        return 0 <= px < w and 0 <= py < h and bool(binary[py, px])

    contour: list[list[float]] = []
    bx, by = start[0] - 1, start[1]
    cx, cy = start
    max_iter = int(binary.size * 4) + 8

    for _ in range(max_iter):
        contour.append([float(cx), float(cy)])
        back = (bx - cx, by - cy)
        try:
            back_i = neighbors.index(back)
        except ValueError:
            back_i = 0
        found = False
        for k in range(1, 9):
            dx, dy = neighbors[(back_i + k) % 8]
            nx, ny = cx + dx, cy + dy
            if is_fg(nx, ny):
                bx, by = cx, cy
                cx, cy = nx, ny
                found = True
                break
        if not found:
            break
        if (cx, cy) == start and len(contour) > 2:
            break

    if len(contour) < 3:
        bb = mask_bbox(mask)
        if bb is None:
            return []
        x0, y0, x1, y1 = bb
        return [
            [float(x0), float(y0)],
            [float(x1 - 1), float(y0)],
            [float(x1 - 1), float(y1 - 1)],
            [float(x0), float(y1 - 1)],
        ]

    return simplify_polyline(contour, max_points=max_points)


def union_masks(masks: Iterable[np.ndarray], height: int, width: int) -> np.ndarray:
    """Logical OR of masks."""
    out = empty_mask(height, width)
    for m in masks:
        if m is None or m.size == 0:
            continue
        if m.shape != out.shape:
            continue
        out = np.maximum(out, ensure_binary_mask(m))
    return out


def connected_mask_parts(
    mask: np.ndarray | None,
    *,
    min_area: int = 50,
    connectivity: int = 1,
) -> list[np.ndarray]:
    """Return connected components of a binary mask as separate uint8 masks.

    Components smaller than ``min_area`` are dropped.

    Parameters
    ----------
    connectivity:
        1 = 4-connected (preferred after erase — diagonal bridges do not
        keep two halves as one object), 2 = 8-connected.
    """
    if mask is None or mask.size == 0 or not np.any(mask):
        return []
    binary = ensure_binary_mask(mask) > 0
    try:
        from skimage import measure
    except ImportError:  # pragma: no cover
        return [ensure_binary_mask(mask)]

    conn = 1 if int(connectivity) <= 1 else 2
    labeled = measure.label(binary, connectivity=conn)
    parts: list[np.ndarray] = []
    for lab in range(1, int(labeled.max()) + 1):
        m = labeled == lab
        if int(m.sum()) < int(min_area):
            continue
        parts.append(ensure_binary_mask(m.astype(np.uint8) * 255))
    return parts


def _densify_polyline(
    points: Sequence[Sequence[float]],
    *,
    step: float = 1.0,
) -> list[tuple[float, float]]:
    """Sample points along a polyline at roughly ``step`` pixel spacing."""
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) == 0:
        return []
    if len(pts) == 1:
        return pts
    out: list[tuple[float, float]] = [pts[0]]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        dist = float(np.hypot(x1 - x0, y1 - y0))
        n = max(int(np.ceil(dist / max(step, 0.5))), 1)
        for k in range(1, n + 1):
            t = k / n
            out.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    return out


def split_mask_by_polylines(
    mask: np.ndarray,
    polylines: Sequence[Sequence[Sequence[float]]],
    *,
    min_area: int = 30,
) -> list[np.ndarray]:
    """Partition a (possibly still-connected) mask by nearest length polyline.

    Each FG pixel is assigned to the closest polyline (Euclidean distance to
    densified samples). Returns one mask per polyline that retains ≥ min_area
    pixels. Used when erase severs the body-length path but a thin mask bridge
    still links two halves under 8-connectivity.
    """
    binary = ensure_binary_mask(mask) > 0
    if not np.any(binary):
        return []
    polys = [list(p) for p in polylines if p and len(p) >= 2]
    if not polys:
        return connected_mask_parts(mask, min_area=min_area, connectivity=1)
    if len(polys) == 1:
        part = ensure_binary_mask(mask)
        return [part] if mask_area_px(part) >= min_area else []

    h, w = binary.shape
    try:
        from scipy import ndimage as ndi
    except ImportError:  # pragma: no cover
        return connected_mask_parts(mask, min_area=min_area, connectivity=1)

    dist_maps: list[np.ndarray] = []
    for poly in polys:
        # False at polyline samples → distance_transform measures dist to them
        not_seed = np.ones((h, w), dtype=bool)
        for x, y in _densify_polyline(poly, step=1.0):
            ix, iy = int(round(x)), int(round(y))
            if 0 <= ix < w and 0 <= iy < h:
                not_seed[iy, ix] = False
        if np.all(not_seed):
            dist_maps.append(np.full((h, w), 1e9, dtype=np.float64))
        else:
            dist_maps.append(ndi.distance_transform_edt(not_seed))

    stack = np.stack(dist_maps, axis=0)
    nearest = np.argmin(stack, axis=0)  # 0..n-1
    parts: list[np.ndarray] = []
    for j in range(len(polys)):
        m = binary & (nearest == j)
        if int(m.sum()) < int(min_area):
            continue
        parts.append(ensure_binary_mask(m.astype(np.uint8) * 255))
    # If nearest assignment collapsed everything into one (degenerate), fall back
    if len(parts) < 2:
        return connected_mask_parts(mask, min_area=min_area, connectivity=1)
    return parts
