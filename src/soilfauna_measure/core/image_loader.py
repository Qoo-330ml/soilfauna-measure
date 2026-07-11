"""Load scientific images for display and future measurement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

SUPPORTED_EXTENSIONS = frozenset(
    {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}
)


class ImageLoadError(Exception):
    """Raised when an image cannot be loaded or interpreted."""


@dataclass(frozen=True)
class ImageMeta:
    """Metadata describing a loaded image."""

    path: Path
    width: int
    height: int
    channels: int
    dtype: str
    format_hint: str


@dataclass(frozen=True)
class LoadedImage:
    """Raw pixel array plus metadata.

    ``raw`` is the measurement-oriented array:
    - grayscale: shape (H, W)
    - color: shape (H, W, C) with C in {3, 4}
    """

    raw: np.ndarray
    meta: ImageMeta


def is_supported_image(path: Path) -> bool:
    """Return True if path has a supported image extension."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def scan_image_files(directory: Path) -> list[Path]:
    """Scan a directory (non-recursive) for supported images.

    Results are sorted by name (case-insensitive).
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    files = [
        p
        for p in directory.iterdir()
        if p.is_file() and is_supported_image(p)
    ]
    return sorted(files, key=lambda p: p.name.lower())


def _dtype_name(arr: np.ndarray) -> str:
    return str(arr.dtype)


def _normalize_array(arr: np.ndarray) -> np.ndarray:
    """Normalize array layout to HxW or HxWxC."""
    if arr.ndim == 2:
        return np.ascontiguousarray(arr)
    if arr.ndim == 3:
        # tifffile may return (C, H, W) for planar samples
        if arr.shape[0] in (3, 4) and arr.shape[0] < arr.shape[-1]:
            # Heuristic: small first dim is channels
            if arr.shape[0] < min(arr.shape[1], arr.shape[2]):
                arr = np.moveaxis(arr, 0, -1)
        if arr.shape[-1] not in (1, 3, 4):
            # Multi-page stack: take first plane if looks like (N, H, W)
            if arr.shape[0] < 32 and arr.shape[1] > 32 and arr.shape[2] > 32:
                arr = arr[0]
                if arr.ndim == 2:
                    return np.ascontiguousarray(arr)
        if arr.shape[-1] == 1:
            arr = arr[..., 0]
        return np.ascontiguousarray(arr)
    if arr.ndim == 4:
        # (pages, H, W, C) or (pages, C, H, W) — use first page
        arr = arr[0]
        return _normalize_array(arr)
    raise ImageLoadError(f"Unsupported array ndim={arr.ndim}, shape={arr.shape}")


def _load_with_tifffile(path: Path) -> np.ndarray:
    import tifffile

    with tifffile.TiffFile(path) as tif:
        if not tif.pages:
            raise ImageLoadError(f"TIFF has no pages: {path}")
        arr = tif.asarray()
    return np.asarray(arr)


def _load_with_pillow(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as im:
        im.load()
        # Preserve bit depth where possible
        arr = np.array(im)
    return arr


def load_image(path: Path | str) -> LoadedImage:
    """Load an image from disk into a numpy array.

    TIFF prefers tifffile; other formats use Pillow.
    """
    path = Path(path)
    if not path.is_file():
        raise ImageLoadError(f"File not found: {path}")
    if not is_supported_image(path):
        raise ImageLoadError(f"Unsupported extension: {path.suffix}")

    suffix = path.suffix.lower()
    try:
        if suffix in {".tif", ".tiff"}:
            try:
                arr = _load_with_tifffile(path)
            except Exception as exc:  # noqa: BLE001 — fall back
                try:
                    arr = _load_with_pillow(path)
                except Exception as exc2:  # noqa: BLE001
                    raise ImageLoadError(
                        f"Failed to load TIFF {path.name}: {exc}; pillow: {exc2}"
                    ) from exc2
        else:
            arr = _load_with_pillow(path)
    except ImageLoadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImageLoadError(f"Failed to load {path.name}: {exc}") from exc

    if arr.size == 0:
        raise ImageLoadError(f"Empty image: {path}")

    arr = _normalize_array(arr)
    if arr.ndim == 2:
        height, width = arr.shape
        channels = 1
    elif arr.ndim == 3:
        height, width, channels = arr.shape
    else:
        raise ImageLoadError(f"Unexpected shape after normalize: {arr.shape}")

    meta = ImageMeta(
        path=path.resolve(),
        width=int(width),
        height=int(height),
        channels=int(channels),
        dtype=_dtype_name(arr),
        format_hint=suffix.lstrip(".") or "unknown",
    )
    return LoadedImage(raw=arr, meta=meta)


def array_to_display_rgb(raw: np.ndarray) -> np.ndarray:
    """Convert raw array to uint8 RGB for display without aggressive auto-contrast.

    - uint8: pass through / expand gray / drop alpha
    - uint16 / other integers: linear scale to 0–255 using full dtype range
      (not histogram stretch), preserving relative brightness.
    """
    if raw.ndim == 2:
        gray = raw
        rgb = np.stack([gray, gray, gray], axis=-1)
    elif raw.ndim == 3 and raw.shape[2] == 1:
        gray = raw[..., 0]
        rgb = np.stack([gray, gray, gray], axis=-1)
    elif raw.ndim == 3 and raw.shape[2] >= 3:
        rgb = raw[..., :3]
    else:
        raise ImageLoadError(f"Cannot convert shape {raw.shape} to RGB")

    if rgb.dtype == np.uint8:
        return np.ascontiguousarray(rgb)

    if np.issubdtype(rgb.dtype, np.integer):
        info = np.iinfo(rgb.dtype)
        scale = 255.0 / float(info.max - info.min) if info.max > info.min else 1.0
        out = (rgb.astype(np.float64) - info.min) * scale
        return np.clip(out, 0, 255).astype(np.uint8)

    # Float: assume 0–1 or 0–255
    f = rgb.astype(np.float64)
    vmax = float(np.nanmax(f)) if f.size else 1.0
    if vmax <= 1.5:
        f = f * 255.0
    return np.clip(f, 0, 255).astype(np.uint8)


def describe_image(loaded: LoadedImage) -> dict[str, Any]:
    """Return a plain dict of basic stats for UI / debugging."""
    raw = loaded.raw
    return {
        "path": str(loaded.meta.path),
        "name": loaded.meta.path.name,
        "width": loaded.meta.width,
        "height": loaded.meta.height,
        "channels": loaded.meta.channels,
        "dtype": loaded.meta.dtype,
        "format": loaded.meta.format_hint,
        "min": float(np.min(raw)) if raw.size else None,
        "max": float(np.max(raw)) if raw.size else None,
        "mean": float(np.mean(raw)) if raw.size else None,
    }
