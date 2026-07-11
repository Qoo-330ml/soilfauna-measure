"""Export masks, crops, and annotated overview images."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from soilfauna_measure.core.image_loader import array_to_display_rgb, load_image
from soilfauna_measure.core.mask_operations import ensure_binary_mask, mask_bbox
from soilfauna_measure.models.category import Category
from soilfauna_measure.models.image_record import ImageRecord
from soilfauna_measure.models.project import Project
from soilfauna_measure.models.specimen import SpecimenObject
from soilfauna_measure.storage.mask_store import load_mask

logger = logging.getLogger(__name__)


def _parse_color(hex_color: str) -> tuple[int, int, int]:
    c = (hex_color or "#007aff").lstrip("#")
    if len(c) == 6:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return 74, 144, 217


def _font(size: int = 14):
    try:
        return ImageFont.truetype("Arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        except OSError:
            return ImageFont.load_default()


def export_masks_for_image(
    workspace_root: Path,
    record: ImageRecord,
    out_dir: Path,
) -> list[Path]:
    """Copy/export each object mask PNG into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for obj in record.objects:
        if not obj.mask_path:
            continue
        try:
            mask = load_mask(workspace_root, obj.mask_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip mask %s: %s", obj.object_id, exc)
            continue
        dest = out_dir / f"{obj.object_id}.png"
        Image.fromarray(ensure_binary_mask(mask), mode="L").save(dest)
        paths.append(dest)
    return paths


def export_crops_for_image(
    workspace_root: Path,
    record: ImageRecord,
    image_abs: Path,
    out_dir: Path,
    *,
    padding: int = 8,
) -> list[Path]:
    """Export RGB crop of each object bounding box."""
    out_dir.mkdir(parents=True, exist_ok=True)
    loaded = load_image(image_abs)
    rgb = array_to_display_rgb(loaded.raw)
    h, w = rgb.shape[:2]
    paths: list[Path] = []
    for obj in record.objects:
        if not obj.mask_path:
            continue
        try:
            mask = load_mask(
                workspace_root,
                obj.mask_path,
                expected_shape=(h, w),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip crop %s: %s", obj.object_id, exc)
            continue
        bb = mask_bbox(mask)
        if bb is None:
            continue
        x0, y0, x1, y1 = bb
        x0 = max(0, x0 - padding)
        y0 = max(0, y0 - padding)
        x1 = min(w, x1 + padding)
        y1 = min(h, y1 + padding)
        crop = rgb[y0:y1, x0:x1]
        dest = out_dir / f"{obj.object_id}_crop.png"
        Image.fromarray(crop, mode="RGB").save(dest)
        paths.append(dest)
    return paths


def render_annotated_image(
    workspace_root: Path,
    record: ImageRecord,
    image_abs: Path,
    categories: list[Category],
    *,
    show_labels: bool = True,
    show_contours: bool = True,
    show_length: bool = True,
) -> Image.Image:
    """Compose RGB annotated overview for one image."""
    loaded = load_image(image_abs)
    rgb = array_to_display_rgb(loaded.raw)
    base = Image.fromarray(rgb, mode="RGB").convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(16)
    cat_map = {c.category_id: c for c in categories}
    h, w = rgb.shape[:2]

    for obj in record.objects:
        cat = cat_map.get(obj.category_id)
        color = _parse_color(cat.color if cat else "#FF4444")
        try:
            mask = load_mask(
                workspace_root,
                obj.mask_path,
                expected_shape=(h, w),
            ) if obj.mask_path else None
        except Exception:
            mask = None

        if mask is not None and np.any(mask):
            # semi-transparent fill
            tint = np.zeros((h, w, 4), dtype=np.uint8)
            fg = mask > 0
            tint[fg, 0] = color[0]
            tint[fg, 1] = color[1]
            tint[fg, 2] = color[2]
            tint[fg, 3] = 70
            overlay = Image.alpha_composite(overlay, Image.fromarray(tint, mode="RGBA"))
            draw = ImageDraw.Draw(overlay)

        if show_contours and obj.contour and len(obj.contour) >= 2:
            pts = [(float(p[0]), float(p[1])) for p in obj.contour]
            if pts[0] != pts[-1]:
                pts = pts + [pts[0]]
            draw.line(pts, fill=color + (220,), width=2)

        if show_length and obj.length_points and len(obj.length_points) >= 2:
            lpts = [(float(p[0]), float(p[1])) for p in obj.length_points]
            draw.line(lpts, fill=(40, 120, 255, 230), width=2)
            for i, (x, y) in enumerate(lpts):
                r = 3
                col = (0, 200, 80, 255) if i in (0, len(lpts) - 1) else (220, 40, 40, 255)
                draw.ellipse([x - r, y - r, x + r, y + r], fill=col)

        if show_labels:
            label = obj.object_id
            if cat:
                label = f"{obj.object_id} {cat.name_zh}"
            # place near contour centroid or bbox
            if obj.contour:
                xs = [p[0] for p in obj.contour]
                ys = [p[1] for p in obj.contour]
                cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            elif mask is not None:
                bb = mask_bbox(mask)
                if bb:
                    cx = (bb[0] + bb[2]) / 2
                    cy = (bb[1] + bb[3]) / 2
                else:
                    cx, cy = 10, 10
            else:
                cx, cy = 10, 10
            draw.text((cx, cy), label, fill=color + (255,), font=font)

    # scale bar
    if record.scale is not None:
        s = record.scale
        x0, y0 = s.start_point
        x1, y1 = s.end_point
        draw.line([(x0, y0), (x1, y1)], fill=(0, 200, 80, 255), width=2)

    out = Image.alpha_composite(base, overlay).convert("RGB")
    return out


def export_annotated_for_image(
    workspace_root: Path,
    record: ImageRecord,
    image_abs: Path,
    categories: list[Category],
    out_path: Path,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = render_annotated_image(
        workspace_root, record, image_abs, categories
    )
    img.save(out_path)
    return out_path
