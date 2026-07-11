"""Traditional instance segmentation for light-background soil fauna images.

Designed for stereo/microscope images with near-white background and
semi-transparent bodies. Default strategy prefers **whole-organism**
instances (less watershed splitting); contact-split is optional.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from scipy import ndimage as ndi
from skimage import color, morphology, measure, segmentation, filters, util
from skimage.feature import peak_local_max
from skimage.morphology import remove_small_holes, remove_small_objects

from soilfauna_measure.core.mask_operations import ensure_binary_mask, mask_to_contour


@dataclass
class SegmentationParams:
    """Tunable parameters for automatic instance segmentation."""

    # Foreground extraction (RGB / multi-space)
    blur_sigma: float = 1.5
    threshold_method: str = "otsu"  # otsu | fixed | triangle
    fixed_threshold: float = 0.10  # on [0,1] score map
    use_lab: bool = True  # use Lab L darkness + chroma vs background
    use_hsv: bool = True  # use V darkness
    score_percentile_clip: float = 99.5  # robust normalize

    # Morphology — stronger close keeps semi-transparent body as one blob
    open_radius: int = 1
    close_radius: int = 6
    hole_area: int = 256
    min_object_area: int = 400
    max_object_area: int = 0  # 0 = no max

    # Watershed — default OFF to avoid cutting one animal into pieces
    enable_watershed: bool = False
    watershed_min_distance: int = 35
    watershed_compactness: float = 0.05
    watershed_min_peak_height: float = 4.0  # distance transform units
    # After watershed, merge fragments that share a long boundary
    merge_thin_splits: bool = True
    merge_boundary_min: int = 12

    # Appendages (legs / antennae): default strip for cleaner body area
    preserve_appendages: bool = False
    # Strength 1–15 (UI). Higher = larger adaptive opening radius vs body thickness.
    appendage_open_radius: int = 7
    appendage_restore_radius: int = 2
    # Opening radius ≈ body_half_width * thickness_frac (mapped by strength)
    appendage_thickness_frac: float = 0.40
    appendage_min_half_width: float = 2.5
    # Cap on opening radius (px); raised so thick-bodied fauna still lose legs
    appendage_max_half_width: float = 14.0

    # Exclude microscope scale bar (usually bottom-right on this dataset)
    exclude_scale_corner: bool = True
    scale_corner_right_frac: float = 0.30  # right 30% of width
    scale_corner_bottom_frac: float = 0.16  # bottom 16% of height
    # Also drop leftover scale-like fragments after labeling
    filter_scale_like: bool = True

    # Strategy preset name (for UI)
    strategy: str = "whole"  # whole | contact_split

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SegmentationParams:
        if not data:
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)

    @classmethod
    def preset_whole(cls) -> SegmentationParams:
        """Prefer one mask per animal; strip thin appendages; no aggressive split."""
        return cls(
            strategy="whole",
            blur_sigma=1.8,
            use_lab=True,
            use_hsv=True,
            open_radius=1,
            close_radius=7,
            hole_area=400,
            min_object_area=500,
            enable_watershed=False,
            preserve_appendages=False,
            appendage_open_radius=7,
            appendage_restore_radius=2,
            appendage_thickness_frac=0.40,
            appendage_min_half_width=2.8,
            appendage_max_half_width=14.0,
            exclude_scale_corner=True,
            filter_scale_like=True,
        )

    @classmethod
    def preset_contact_split(cls) -> SegmentationParams:
        """Try to split touching animals with conservative watershed."""
        return cls(
            strategy="contact_split",
            blur_sigma=1.5,
            use_lab=True,
            use_hsv=True,
            open_radius=1,
            close_radius=5,
            hole_area=256,
            min_object_area=400,
            enable_watershed=True,
            watershed_min_distance=40,
            watershed_min_peak_height=6.0,
            watershed_compactness=0.08,
            merge_thin_splits=True,
            merge_boundary_min=15,
            preserve_appendages=False,
            appendage_open_radius=7,
            appendage_restore_radius=2,
            appendage_thickness_frac=0.40,
            appendage_min_half_width=2.8,
            appendage_max_half_width=14.0,
            exclude_scale_corner=True,
            filter_scale_like=True,
        )


@dataclass
class InstanceMask:
    """One segmented instance."""

    label: int
    mask: np.ndarray  # uint8 0/255
    area_px: int
    contour: list[list[float]] = field(default_factory=list)


@dataclass
class SegmentationResult:
    foreground: np.ndarray  # uint8 binary
    instances: list[InstanceMask]
    labels: np.ndarray  # int labels, 0 background
    params: SegmentationParams
    message: str = ""


class SegmentationError(Exception):
    """Segmentation failed in a controlled way."""


def _to_float_rgb(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        g = util.img_as_float(image)
        return np.stack([g, g, g], axis=-1)
    if image.ndim == 3 and image.shape[2] >= 3:
        rgb = image[..., :3]
        return util.img_as_float(rgb)
    if image.ndim == 3 and image.shape[2] == 1:
        g = util.img_as_float(image[..., 0])
        return np.stack([g, g, g], axis=-1)
    raise SegmentationError(f"Unsupported image shape: {image.shape}")


def _estimate_background(rgb: np.ndarray, border: int = 24) -> np.ndarray:
    """Estimate bright background RGB from image borders."""
    h, w = rgb.shape[:2]
    b = max(2, min(border, h // 8, w // 8))
    strips = [
        rgb[:b, :, :],
        rgb[-b:, :, :],
        rgb[:, :b, :],
        rgb[:, -b:, :],
    ]
    samples = np.concatenate([s.reshape(-1, 3) for s in strips], axis=0)
    brightness = samples.mean(axis=1)
    bright = samples[brightness >= np.percentile(brightness, 70)]
    if len(bright) < 10:
        bright = samples
    return np.median(bright, axis=0)


def _robust_norm(x: np.ndarray, pct: float = 99.5) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    hi = float(np.percentile(x, pct)) if x.size else 1.0
    if hi <= 1e-12:
        hi = float(x.max()) if x.size and x.max() > 0 else 1.0
    return np.clip(x / hi, 0.0, 1.0)


def extract_foreground(
    image: np.ndarray,
    params: SegmentationParams | None = None,
) -> np.ndarray:
    """Return binary foreground using multi-channel RGB/Lab/HSV cues.

    Animals on white background are darker and often slightly tinted; we fuse:
    - RGB Euclidean distance from estimated background
    - Gray / Lab-L darkness relative to background
    - Optional Lab chroma distance and HSV value darkness
    """
    params = params or SegmentationParams()
    rgb = _to_float_rgb(image)
    bg = _estimate_background(rgb)
    bg_l = float(np.mean(bg))

    # RGB distance from background color
    rgb_diff = np.linalg.norm(rgb - bg.reshape(1, 1, 3), axis=2)
    gray = color.rgb2gray(rgb)
    darkness = np.clip(bg_l - gray, 0.0, None)

    parts = [
        0.40 * _robust_norm(rgb_diff, params.score_percentile_clip),
        0.35 * _robust_norm(darkness, params.score_percentile_clip),
    ]
    w_sum = 0.75

    if params.use_lab:
        lab = color.rgb2lab(rgb)
        # L in Lab is ~0..100
        bg_lab = color.rgb2lab(bg.reshape(1, 1, 3)).reshape(3)
        lab_diff = np.linalg.norm(lab - bg_lab.reshape(1, 1, 3), axis=2)
        L_dark = np.clip(float(bg_lab[0]) - lab[..., 0], 0.0, None)
        parts.append(0.15 * _robust_norm(lab_diff, params.score_percentile_clip))
        parts.append(0.15 * _robust_norm(L_dark, params.score_percentile_clip))
        w_sum += 0.30

    if params.use_hsv:
        hsv = color.rgb2hsv(rgb)
        # V channel darkness
        v_dark = np.clip(float(np.median(bg)) - hsv[..., 2], 0.0, None)
        # mild saturation (debris vs animal: animals often weakly saturated)
        sat = hsv[..., 1]
        parts.append(0.10 * _robust_norm(v_dark, params.score_percentile_clip))
        parts.append(0.05 * _robust_norm(sat * v_dark, params.score_percentile_clip))
        w_sum += 0.15

    score = sum(parts)
    # re-normalize combined score
    score = _robust_norm(score, 99.8)

    # Mild blur to bridge semi-transparent gaps inside body
    if params.blur_sigma > 0:
        score = filters.gaussian(score, sigma=params.blur_sigma, preserve_range=True)
        score = _robust_norm(score, 99.8)

    if params.threshold_method == "fixed":
        thr = float(params.fixed_threshold)
        fg = score > thr
    elif params.threshold_method == "triangle":
        try:
            thr = filters.threshold_triangle(score)
            fg = score > thr
        except ValueError:
            thr = float(np.percentile(score, 80))
            fg = score > thr
    else:
        try:
            thr = filters.threshold_otsu(score)
            fg = score > thr
        except ValueError:
            fg = score > np.percentile(score, 82)

    # If almost nothing, loosen; if too much, tighten
    frac = float(fg.mean()) if fg.size else 0.0
    if frac < 0.005:
        fg = score > np.percentile(score, 88)
    elif frac > 0.40:
        fg = score > max(thr if "thr" in dir() else 0.2, float(np.percentile(score, 92)))

    return fg


def clear_scale_corner(
    fg: np.ndarray,
    *,
    right_frac: float = 0.30,
    bottom_frac: float = 0.16,
) -> np.ndarray:
    """Zero out bottom-right corner where scale bars usually sit.

    Does not touch the rest of the field; animals in the main plate stay intact.
    """
    out = fg.astype(bool).copy()
    h, w = out.shape
    if h < 8 or w < 8:
        return out
    rf = float(np.clip(right_frac, 0.05, 0.5))
    bf = float(np.clip(bottom_frac, 0.05, 0.4))
    x0 = int(w * (1.0 - rf))
    y0 = int(h * (1.0 - bf))
    out[y0:, x0:] = False
    # Also clear a thin full bottom strip for scale bars drawn across the bottom
    # (only the lower ~6% to avoid animals sitting mid-lower field)
    y_strip = int(h * 0.94)
    out[y_strip:, :] = False
    return out


def _bbox_stats(mask: np.ndarray) -> tuple[int, int, int, int, float, float, float]:
    """Return x0,y0,x1,y1, cx, cy, aspect (max/min side)."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return 0, 0, 0, 0, 0.0, 0.0, 1.0
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw = max(1, x1 - x0 + 1)
    bh = max(1, y1 - y0 + 1)
    aspect = max(bw, bh) / min(bw, bh)
    return x0, y0, x1, y1, float(xs.mean()), float(ys.mean()), float(aspect)


def is_scale_like_instance(
    mask: np.ndarray,
    *,
    image_shape: tuple[int, int],
    right_frac: float = 0.35,
    bottom_frac: float = 0.20,
) -> bool:
    """Heuristic: scale bar / scale text in image margin.

    Typical cues on soil-fauna plates:
    - located in bottom-right (or thin bottom strip)
    - moderately small area relative to field
    - elongated horizontal box (the bar) or compact near corner (digits)
    """
    h, w = image_shape
    area = int(np.count_nonzero(mask))
    if area <= 0:
        return True
    x0, y0, x1, y1, cx, cy, aspect = _bbox_stats(mask > 0)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1

    in_br = (cx >= w * (1.0 - right_frac)) and (cy >= h * (1.0 - bottom_frac))
    in_bottom_strip = cy >= h * 0.90
    # horizontal ruler-like
    horizontal_bar = (bw >= bh * 2.0) and (bh <= h * 0.08) and (cy >= h * 0.85)
    # small debris/text in BR corner
    small_br = in_br and area < (h * w * 0.01)
    # almost fully inside BR corner box
    box_x0, box_y0 = int(w * (1.0 - right_frac)), int(h * (1.0 - bottom_frac))
    mostly_in_corner = x0 >= box_x0 - 5 and y0 >= box_y0 - 5

    if horizontal_bar and (in_br or in_bottom_strip):
        return True
    if small_br and mostly_in_corner:
        return True
    if in_br and mostly_in_corner and aspect >= 2.0:
        return True
    # top-left dirt / sensor dust common on plates — optional light filter
    if cx < w * 0.08 and cy < h * 0.08 and area < 2000:
        return True
    return False


def _strip_one_component(
    comp: np.ndarray,
    *,
    strength: int,
    restore_radius: int,
    thickness_frac: float,
    min_half_width: float,
    max_half_width: float,
) -> np.ndarray:
    """Body-only mask for a single connected component.

    Uses adaptive morphological opening (true width filter): features thinner
    than ~2*r are removed. Unlike DT-core + large dilation, opening does not
    re-grow legs after they have been eroded away.
    """
    dist = ndi.distance_transform_edt(comp)
    vals = dist[comp]
    if vals.size == 0:
        return comp

    p80 = float(np.percentile(vals, 80))
    p90 = float(np.percentile(vals, 90))
    body_hw = 0.55 * p80 + 0.45 * p90
    max_hw = float(dist.max())

    # Very thin overall object: light clean only
    if body_hw < max(2.0, float(min_half_width) * 0.85):
        return morphology.opening(comp, morphology.disk(1))

    # strength 1..15 → opening radius as fraction of body half-width
    # strength 7 (default) ≈ thickness_frac; higher strength peels thicker limbs
    s = max(1, int(strength))
    frac = float(thickness_frac) * (1.0 + 0.06 * (s - 7))
    frac = float(np.clip(frac, 0.22, 0.58))

    r = int(round(body_hw * frac))
    r = max(2, min(r, int(round(float(max_half_width))), int(max_hw * 0.48), 20))

    opened = morphology.opening(comp, morphology.disk(r))
    if not np.any(opened):
        for r2 in range(r - 1, 1, -1):
            opened = morphology.opening(comp, morphology.disk(r2))
            if np.any(opened):
                r = r2
                break
        if not np.any(opened):
            return comp

    # Reconnect semi-transparent body gaps without bridging long limbs
    gap_r = max(1, min(3, r // 3))
    opened = morphology.closing(opened, morphology.disk(gap_r))

    # Keep only fragments that still look like body (have real thickness)
    thr = max(float(min_half_width), body_hw * 0.38)
    thr = min(thr, max_hw * 0.50)
    lb = measure.label(opened)
    nlab = int(lb.max())
    if nlab == 0:
        return comp

    keep = np.zeros_like(opened)
    min_frag = max(40, int(comp.sum() * 0.02))
    for lid in range(1, nlab + 1):
        part = lb == lid
        area = int(part.sum())
        if area < min_frag:
            continue
        part_max = float(dist[part].max()) if np.any(part) else 0.0
        # Body core: thick enough, or a large share of the opened mass
        if part_max >= thr or area >= max(min_frag * 3, int(opened.sum() * 0.25)):
            keep |= part

    if not np.any(keep):
        # Fallback: largest opened fragment
        sizes = np.bincount(lb.ravel())
        sizes[0] = 0
        keep = lb == int(np.argmax(sizes))

    # Minimal edge restore only — large restore was re-growing legs
    restore = max(0, min(int(restore_radius), 3, max(1, r // 4)))
    if restore > 0:
        body = morphology.dilation(keep, morphology.disk(restore)) & comp
    else:
        body = keep

    # Drop residual hairline spikes
    body = morphology.opening(body, morphology.disk(1))
    if not np.any(body):
        return keep
    return body


def strip_thin_appendages(
    mask: np.ndarray,
    *,
    open_radius: int = 7,
    restore_radius: int = 2,
    thickness_frac: float = 0.40,
    min_half_width: float = 2.5,
    max_half_width: float = 14.0,
) -> np.ndarray:
    """Remove thin protrusions (legs, antennae); keep thick body.

    Processes each connected component with an adaptive morphological opening
    sized from that component's body half-width. Opening removes structures
    thinner than ~2×radius; only a *small* dilation restores jagged body edges
    (previous DT-core + large dilation was re-attaching limbs).
    """
    binary = mask.astype(bool) if mask.dtype != bool else mask.copy()
    if not np.any(binary):
        return binary

    labeled = measure.label(binary)
    n = int(labeled.max())
    if n == 0:
        return binary

    strength = max(1, int(open_radius))
    out = np.zeros_like(binary)

    if n == 1:
        out = _strip_one_component(
            binary,
            strength=strength,
            restore_radius=int(restore_radius),
            thickness_frac=float(thickness_frac),
            min_half_width=float(min_half_width),
            max_half_width=float(max_half_width),
        )
        return out

    for lid in range(1, n + 1):
        comp = labeled == lid
        if not np.any(comp):
            continue
        out |= _strip_one_component(
            comp,
            strength=strength,
            restore_radius=int(restore_radius),
            thickness_frac=float(thickness_frac),
            min_half_width=float(min_half_width),
            max_half_width=float(max_half_width),
        )
    return out


def _morph_clean(fg: np.ndarray, params: SegmentationParams) -> np.ndarray:
    """Morphological cleanup.

    Body-only path (default): strip thin limbs **before** heavy closing
    (closing would thicken legs and make them hard to remove), then close to
    reconnect semi-transparent body gaps.
    """
    out = fg.astype(bool)

    if params.preserve_appendages:
        close_r = params.close_radius
        open_r = max(0, min(params.open_radius, 1))
        if close_r > 0:
            out = morphology.closing(out, morphology.disk(close_r))
        if open_r > 0:
            out = morphology.opening(out, morphology.disk(open_r))
        if close_r > 1:
            se = morphology.disk(max(1, close_r // 2))
            out = morphology.dilation(out, se)
            out = morphology.erosion(out, se)
        if params.hole_area > 0:
            try:
                out = remove_small_holes(out, max_size=params.hole_area)
            except TypeError:
                out = remove_small_holes(out, area_threshold=params.hole_area)
    else:
        # 1) Minimal denoise only — do NOT thicken limbs before strip
        out = morphology.opening(out, morphology.disk(1))
        # 2) Strip thin appendages (per-component adaptive opening)
        out = strip_thin_appendages(
            out,
            open_radius=int(params.appendage_open_radius),
            restore_radius=int(params.appendage_restore_radius),
            thickness_frac=float(params.appendage_thickness_frac),
            min_half_width=float(params.appendage_min_half_width),
            max_half_width=float(params.appendage_max_half_width),
        )
        # 3) Reconnect body / fill semi-transparent gaps (cap SE so stubs
        #    of removed legs are not bridged back onto the body)
        body_close = max(2, min(int(params.close_radius), 5))
        out = morphology.closing(out, morphology.disk(body_close))
        if params.hole_area > 0:
            try:
                out = remove_small_holes(out, max_size=params.hole_area)
            except TypeError:
                out = remove_small_holes(out, area_threshold=params.hole_area)
        # 4) Final light open — closing can re-bridge short limb stubs
        out = morphology.opening(out, morphology.disk(2))

    if params.min_object_area > 0:
        try:
            out = remove_small_objects(out, max_size=params.min_object_area)
        except TypeError:
            out = remove_small_objects(out, min_size=params.min_object_area)
    return out


def _merge_labels_by_boundary(
    labels: np.ndarray,
    *,
    min_boundary: int = 12,
) -> np.ndarray:
    """Merge adjacent labels that share a long boundary (fix over-segmentation)."""
    labels = labels.copy()
    if labels.max() < 2:
        return labels

    # Count boundary adjacencies between label pairs
    h, w = labels.shape
    pairs: dict[tuple[int, int], int] = {}
    for dy, dx in ((0, 1), (1, 0)):
        a = labels[dy:, dx:] if dy or dx else labels
        b = labels[: h - dy, : w - dx] if dy or dx else labels
        mask = (a > 0) & (b > 0) & (a != b)
        if not np.any(mask):
            continue
        aa = a[mask].ravel()
        bb = b[mask].ravel()
        for x, y in zip(aa.tolist(), bb.tolist()):
            key = (min(x, y), max(x, y))
            pairs[key] = pairs.get(key, 0) + 1

    # Union-find merge
    parent = {i: i for i in range(int(labels.max()) + 1)}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for (a, b), cnt in pairs.items():
        if cnt >= min_boundary:
            # Prefer merging only if one is much smaller? For now merge long contacts
            # that look like watershed cuts through one body (long shared edge)
            union(a, b)

    # Remap
    new_id: dict[int, int] = {0: 0}
    nxt = 1
    out = np.zeros_like(labels)
    for lab in range(1, int(labels.max()) + 1):
        root = find(lab)
        if root not in new_id:
            new_id[root] = nxt
            nxt += 1
        out[labels == lab] = new_id[root]
    return out


def split_touching_watershed(
    fg: np.ndarray,
    params: SegmentationParams,
) -> np.ndarray:
    """Label instances; watershed only when enabled and peaks are strong."""
    fg = fg.astype(bool)
    if not np.any(fg):
        return np.zeros(fg.shape, dtype=np.int32)

    if not params.enable_watershed:
        return measure.label(fg).astype(np.int32)

    distance = ndi.distance_transform_edt(fg)
    min_dist = max(1, int(params.watershed_min_distance))
    # Only keep strong peaks (body centers), ignore limb local maxima
    coords = peak_local_max(
        distance,
        min_distance=min_dist,
        labels=fg,
        exclude_border=False,
        threshold_abs=float(params.watershed_min_peak_height),
    )
    if len(coords) == 0:
        return measure.label(fg).astype(np.int32)

    # If a connected component has only one peak, no need to watershed it
    base = measure.label(fg)
    mask_peaks = np.zeros(distance.shape, dtype=bool)
    mask_peaks[tuple(coords.T)] = True

    # Keep at most peaks that fall in multi-peak components
    markers = np.zeros(distance.shape, dtype=np.int32)
    mid = 1
    for comp_id in range(1, int(base.max()) + 1):
        comp = base == comp_id
        ys, xs = np.where(mask_peaks & comp)
        if len(ys) <= 1:
            # single or no peak: keep whole component as one label
            markers[comp] = mid
            mid += 1
            continue
        # multiple peaks → watershed only inside this component
        local_markers = np.zeros_like(markers)
        for y, x in zip(ys, xs):
            local_markers[y, x] = mid
            mid += 1
        local_markers = morphology.dilation(local_markers, morphology.disk(2))
        local_markers = local_markers * comp
        dist_c = distance * comp
        part = segmentation.watershed(
            -dist_c,
            local_markers,
            mask=comp,
            compactness=float(params.watershed_compactness),
        )
        markers[comp] = part[comp]

    labels = markers.astype(np.int32)
    if params.merge_thin_splits:
        labels = _merge_labels_by_boundary(
            labels, min_boundary=int(params.merge_boundary_min)
        )
    return labels


def labels_to_instances(
    labels: np.ndarray,
    params: SegmentationParams,
    *,
    image_shape: tuple[int, int] | None = None,
) -> list[InstanceMask]:
    instances: list[InstanceMask] = []
    h, w = image_shape if image_shape is not None else labels.shape
    for lab in range(1, int(labels.max()) + 1):
        m = labels == lab
        # Per-instance adaptive strip (object-size aware)
        if not params.preserve_appendages:
            m = strip_thin_appendages(
                m,
                open_radius=int(params.appendage_open_radius),
                restore_radius=int(params.appendage_restore_radius),
                thickness_frac=float(params.appendage_thickness_frac),
                min_half_width=float(params.appendage_min_half_width),
                max_half_width=float(params.appendage_max_half_width),
            )
        area = int(m.sum())
        if area < params.min_object_area:
            continue
        if params.max_object_area > 0 and area > params.max_object_area:
            continue
        if params.filter_scale_like and is_scale_like_instance(
            m,
            image_shape=(h, w),
            right_frac=params.scale_corner_right_frac + 0.05,
            bottom_frac=params.scale_corner_bottom_frac + 0.04,
        ):
            continue
        mask = ensure_binary_mask(m.astype(np.uint8) * 255)
        contour = mask_to_contour(mask)
        instances.append(
            InstanceMask(label=lab, mask=mask, area_px=area, contour=contour)
        )
    instances.sort(key=lambda i: -i.area_px)
    return instances


def segment_instances(
    image: np.ndarray,
    params: SegmentationParams | None = None,
) -> SegmentationResult:
    """Full pipeline: RGB multi-cue foreground → morph clean → label/watershed."""
    params = params or SegmentationParams.preset_whole()
    try:
        fg = extract_foreground(image, params)
        fg = _morph_clean(fg, params)
        if params.exclude_scale_corner:
            fg = clear_scale_corner(
                fg,
                right_frac=params.scale_corner_right_frac,
                bottom_frac=params.scale_corner_bottom_frac,
            )
        if not np.any(fg):
            return SegmentationResult(
                foreground=ensure_binary_mask(fg.astype(np.uint8)),
                instances=[],
                labels=np.zeros(fg.shape, dtype=np.int32),
                params=params,
                message="未检测到前景，请调低阈值或减小最小面积",
            )
        labels = split_touching_watershed(fg, params)
        instances = labels_to_instances(
            labels, params, image_shape=fg.shape
        )
        mode = "整虫优先" if not params.enable_watershed else "接触拆分"
        return SegmentationResult(
            foreground=ensure_binary_mask(fg.astype(np.uint8) * 255),
            instances=instances,
            labels=labels,
            params=params,
            message=f"[{mode}] 检测到 {len(instances)} 个实例（已排除比例尺区域）",
        )
    except SegmentationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SegmentationError(str(exc)) from exc


def merge_masks(masks: list[np.ndarray]) -> np.ndarray:
    """Union of binary masks."""
    if not masks:
        raise ValueError("No masks to merge")
    out = np.zeros_like(masks[0], dtype=np.uint8)
    for m in masks:
        out = np.maximum(out, ensure_binary_mask(m))
    return out


def split_mask_by_cut_line(
    mask: np.ndarray,
    polyline: list[list[float]],
    *,
    line_width: int = 3,
    min_area: int = 50,
) -> list[np.ndarray]:
    """Erase a thick polyline from mask and return connected components."""
    from PIL import Image, ImageDraw

    binary = ensure_binary_mask(mask)
    h, w = binary.shape
    img = Image.fromarray(binary, mode="L")
    draw = ImageDraw.Draw(img)
    if len(polyline) >= 2:
        pts = [(float(p[0]), float(p[1])) for p in polyline]
        draw.line(pts, fill=0, width=max(1, int(line_width)))
    r = max(1, line_width // 2)
    for p in polyline:
        x, y = float(p[0]), float(p[1])
        draw.ellipse([x - r, y - r, x + r, y + r], fill=0)

    cut = ensure_binary_mask(np.array(img))
    labeled = measure.label(cut > 0)
    parts: list[np.ndarray] = []
    for lab in range(1, int(labeled.max()) + 1):
        m = labeled == lab
        if int(m.sum()) < min_area:
            continue
        parts.append(ensure_binary_mask(m.astype(np.uint8) * 255))
    return parts


def split_mask_by_seeds(
    mask: np.ndarray,
    seeds: list[tuple[float, float]],
    *,
    min_area: int = 50,
) -> list[np.ndarray]:
    """Watershed split inside mask using user seed points."""
    binary = mask > 0
    if not np.any(binary) or len(seeds) < 2:
        return [ensure_binary_mask(mask)] if np.any(binary) else []

    markers = np.zeros(binary.shape, dtype=np.int32)
    h, w = binary.shape
    for i, (x, y) in enumerate(seeds, start=1):
        ix, iy = int(round(x)), int(round(y))
        if 0 <= ix < w and 0 <= iy < h and binary[iy, ix]:
            markers[iy, ix] = i
        else:
            ys, xs = np.nonzero(binary)
            if len(xs) == 0:
                continue
            d = (xs - ix) ** 2 + (ys - iy) ** 2
            j = int(np.argmin(d))
            markers[ys[j], xs[j]] = i

    if markers.max() < 2:
        return [ensure_binary_mask(mask)]

    markers = morphology.dilation(markers, morphology.disk(2))
    markers = markers * binary
    distance = ndi.distance_transform_edt(binary)
    labels = segmentation.watershed(-distance, markers, mask=binary)
    parts: list[np.ndarray] = []
    for lab in range(1, int(labels.max()) + 1):
        m = labels == lab
        if int(m.sum()) < min_area:
            continue
        parts.append(ensure_binary_mask(m.astype(np.uint8) * 255))
    return parts
