"""Measurement pure functions: polyline body length, etc."""

from __future__ import annotations

from typing import Sequence

from soilfauna_measure.core.calibration import length_px_to_real
from soilfauna_measure.core.coordinate_utils import pixel_distance
from soilfauna_measure.models.calibration import ScaleCalibration


def polyline_length_px(points: Sequence[Sequence[float]]) -> float:
    """Sum of segment lengths for an ordered polyline in image pixels."""
    if points is None or len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points) - 1):
        x0, y0 = float(points[i][0]), float(points[i][1])
        x1, y1 = float(points[i + 1][0]), float(points[i + 1][1])
        total += pixel_distance(x0, y0, x1, y1)
    return float(total)


def copy_points(points: Sequence[Sequence[float]] | None) -> list[list[float]]:
    """Deep-copy point list as [[x,y], ...]."""
    if not points:
        return []
    return [[float(p[0]), float(p[1])] for p in points]


def reverse_points(points: Sequence[Sequence[float]]) -> list[list[float]]:
    pts = copy_points(points)
    pts.reverse()
    return pts


def insert_point(
    points: Sequence[Sequence[float]],
    index: int,
    x: float,
    y: float,
) -> list[list[float]]:
    """Insert point at index (0..len)."""
    pts = copy_points(points)
    idx = max(0, min(int(index), len(pts)))
    pts.insert(idx, [float(x), float(y)])
    return pts


def remove_point(points: Sequence[Sequence[float]], index: int) -> list[list[float]]:
    pts = copy_points(points)
    if 0 <= index < len(pts):
        pts.pop(index)
    return pts


def move_point(
    points: Sequence[Sequence[float]],
    index: int,
    x: float,
    y: float,
) -> list[list[float]]:
    pts = copy_points(points)
    if 0 <= index < len(pts):
        pts[index] = [float(x), float(y)]
    return pts


def nearest_point_index(
    points: Sequence[Sequence[float]],
    x: float,
    y: float,
    *,
    max_dist: float = 10.0,
) -> int | None:
    """Return index of nearest point within max_dist, else None."""
    if not points:
        return None
    best_i = None
    best_d = float(max_dist)
    for i, p in enumerate(points):
        d = pixel_distance(x, y, float(p[0]), float(p[1]))
        if d <= best_d:
            best_d = d
            best_i = i
    return best_i


def nearest_segment_insert(
    points: Sequence[Sequence[float]],
    x: float,
    y: float,
    *,
    max_dist: float = 8.0,
) -> tuple[int, float, float] | None:
    """If (x,y) is near a segment, return (insert_index, px, py) for insert after i.

    insert_index is the index at which to insert the new point (i+1).
    """
    if points is None or len(points) < 2:
        return None
    best = None
    best_d = float(max_dist)
    for i in range(len(points) - 1):
        x0, y0 = float(points[i][0]), float(points[i][1])
        x1, y1 = float(points[i + 1][0]), float(points[i + 1][1])
        px, py, dist = _project_point_to_segment(x, y, x0, y0, x1, y1)
        # Prefer interior of segment (not endpoints)
        if dist < best_d:
            # skip if too close to endpoints (use point hit instead)
            if pixel_distance(px, py, x0, y0) < 3 or pixel_distance(px, py, x1, y1) < 3:
                continue
            best_d = dist
            best = (i + 1, px, py)
    return best


def _project_point_to_segment(
    x: float,
    y: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> tuple[float, float, float]:
    """Return (proj_x, proj_y, distance) of point to segment."""
    dx, dy = x1 - x0, y1 - y0
    len2 = dx * dx + dy * dy
    if len2 <= 1e-12:
        return x0, y0, pixel_distance(x, y, x0, y0)
    t = ((x - x0) * dx + (y - y0) * dy) / len2
    t = max(0.0, min(1.0, t))
    px, py = x0 + t * dx, y0 + t * dy
    return px, py, pixel_distance(x, y, px, py)


def apply_length_to_object(
    length_points: Sequence[Sequence[float]],
    scale: ScaleCalibration | None,
) -> dict:
    """Compute length fields from points. Returns dict of field updates."""
    pts = copy_points(length_points)
    length_px = polyline_length_px(pts)
    result = {
        "length_points": pts,
        "length_px": length_px if len(pts) >= 2 else None,
        "length_um": length_px_to_real(length_px, scale, "um") if len(pts) >= 2 else None,
        "length_mm": length_px_to_real(length_px, scale, "mm") if len(pts) >= 2 else None,
        "length_source": "manual" if pts else "none",
    }
    if not pts:
        result["length_px"] = None
        result["length_um"] = None
        result["length_mm"] = None
        result["length_source"] = "none"
    return result


def _point_near_mask(
    mask,
    x: float,
    y: float,
    *,
    margin: int = 2,
) -> bool:
    """True if any FG pixel lies within Chebyshev margin of (x,y)."""
    import numpy as np

    h, w = mask.shape[:2]
    ix, iy = int(np.floor(x)), int(np.floor(y))
    m = max(0, int(margin))
    x0, x1 = max(0, ix - m), min(w, ix + m + 1)
    y0, y1 = max(0, iy - m), min(h, iy + m + 1)
    if x0 >= x1 or y0 >= y1:
        return False
    return bool(np.any(mask[y0:y1, x0:x1] > 0))


def _segment_on_mask(
    mask,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    margin: int = 2,
    sample_step: float = 1.5,
) -> bool:
    """Sample the segment; False if any sample leaves the remaining mask."""
    import numpy as np

    dist = pixel_distance(x0, y0, x1, y1)
    n = max(int(np.ceil(dist / max(sample_step, 0.5))), 1)
    for k in range(n + 1):
        t = k / n
        x = x0 + t * (x1 - x0)
        y = y0 + t * (y1 - y0)
        if not _point_near_mask(mask, x, y, margin=margin):
            return False
    return True


def split_length_path_by_mask(
    points: Sequence[Sequence[float]] | None,
    mask,
    *,
    margin: int = 2,
) -> list[list[list[float]]]:
    """Split a body-length polyline where it leaves the remaining mask.

    Used after erasing: segments that cross wiped regions break the path into
    independent runs (each with ≥2 points). Empty / fully erased → [].
    """
    pts = copy_points(points)
    if len(pts) < 2 or mask is None:
        return []

    runs: list[list[list[float]]] = []
    # Start only if first point is still on mask
    current: list[list[float]] = []
    if _point_near_mask(mask, pts[0][0], pts[0][1], margin=margin):
        current = [pts[0]]

    for i in range(1, len(pts)):
        p0 = pts[i - 1]
        p1 = pts[i]
        p1_on = _point_near_mask(mask, p1[0], p1[1], margin=margin)
        if (
            current
            and p1_on
            and _segment_on_mask(
                mask, p0[0], p0[1], p1[0], p1[1], margin=margin
            )
        ):
            current.append(p1)
        else:
            if len(current) >= 2:
                runs.append(current)
            current = [p1] if p1_on else []

    if len(current) >= 2:
        runs.append(current)
    return runs


def longest_length_run(
    runs: Sequence[Sequence[Sequence[float]]],
) -> list[list[float]]:
    """Pick the geometrically longest run (need ≥2 points)."""
    best: list[list[float]] = []
    best_l = -1.0
    for r in runs:
        pts = copy_points(r)
        if len(pts) < 2:
            continue
        L = polyline_length_px(pts)
        if L > best_l:
            best_l = L
            best = pts
    return best
