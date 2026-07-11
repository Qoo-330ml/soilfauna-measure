"""Thumbnail generation and disk cache under workspace/thumbnails/."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from soilfauna_measure.core.image_loader import array_to_display_rgb, load_image

logger = logging.getLogger(__name__)

THUMB_SIZE = 96
THUMB_QUALITY = 80


def thumbnail_path(workspace_root: Path, image_stem: str) -> Path:
    return Path(workspace_root) / "thumbnails" / f"{image_stem}.jpg"


def is_thumbnail_fresh(thumb: Path, source: Path) -> bool:
    if not thumb.is_file() or not source.is_file():
        return False
    try:
        return thumb.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def generate_thumbnail(
    source: Path,
    dest: Path,
    *,
    size: int = THUMB_SIZE,
) -> Path:
    """Create a JPEG thumbnail for display list. Source is never modified."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    loaded = load_image(source)
    rgb = array_to_display_rgb(loaded.raw)
    img = Image.fromarray(rgb, mode="RGB")
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    # pad to square for uniform icons
    canvas = Image.new("RGB", (size, size), (40, 40, 42))
    ox = (size - img.width) // 2
    oy = (size - img.height) // 2
    canvas.paste(img, (ox, oy))
    canvas.save(dest, format="JPEG", quality=THUMB_QUALITY, optimize=True)
    return dest


def ensure_thumbnail(
    workspace_root: Path,
    source: Path,
    *,
    image_stem: str | None = None,
    size: int = THUMB_SIZE,
) -> Path | None:
    """Return path to cached thumbnail, generating if needed."""
    stem = image_stem or source.stem
    thumb = thumbnail_path(workspace_root, stem)
    try:
        if is_thumbnail_fresh(thumb, source):
            return thumb
        return generate_thumbnail(source, thumb, size=size)
    except Exception:  # noqa: BLE001
        logger.exception("Thumbnail failed for %s", source)
        return None
