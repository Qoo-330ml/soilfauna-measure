"""Load/save per-object binary masks as PNG."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from soilfauna_measure.core.mask_operations import ensure_binary_mask

logger = logging.getLogger(__name__)


class MaskStoreError(Exception):
    """Mask I/O failure."""


def mask_relative_path(object_id: str) -> str:
    """Relative path used in project JSON."""
    safe = object_id.replace("/", "_").replace("\\", "_")
    return f"masks/{safe}.png"


def mask_absolute_path(workspace_root: Path, object_id: str) -> Path:
    return Path(workspace_root) / mask_relative_path(object_id)


def save_mask(
    workspace_root: Path | str,
    object_id: str,
    mask: np.ndarray,
) -> str:
    """Write mask PNG; return relative path."""
    root = Path(workspace_root)
    rel = mask_relative_path(object_id)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    binary = ensure_binary_mask(mask)
    Image.fromarray(binary, mode="L").save(path, format="PNG", optimize=True)
    logger.debug("Saved mask %s shape=%s area=%s", path, binary.shape, int(np.count_nonzero(binary)))
    return rel.replace("\\", "/")


def load_mask(
    workspace_root: Path | str,
    relative_or_id: str,
    *,
    expected_shape: tuple[int, int] | None = None,
) -> np.ndarray:
    """Load mask from relative path or object_id."""
    root = Path(workspace_root)
    rel = relative_or_id
    if not rel.startswith("masks/") and not rel.endswith(".png"):
        rel = mask_relative_path(relative_or_id)
    path = root / rel
    if not path.is_file():
        # try by object id basename
        alt = mask_absolute_path(root, Path(rel).stem)
        if alt.is_file():
            path = alt
        else:
            raise MaskStoreError(f"Mask not found: {path}")
    try:
        with Image.open(path) as im:
            im = im.convert("L")
            arr = np.array(im)
    except OSError as exc:
        raise MaskStoreError(f"Cannot read mask {path}: {exc}") from exc

    arr = ensure_binary_mask(arr)
    if expected_shape is not None and arr.shape != expected_shape:
        # Resize with nearest if mismatch (should be rare)
        h, w = expected_shape
        img = Image.fromarray(arr, mode="L").resize((w, h), Image.Resampling.NEAREST)
        arr = ensure_binary_mask(np.array(img))
    return arr


def delete_mask(workspace_root: Path | str, object_id: str) -> None:
    path = mask_absolute_path(Path(workspace_root), object_id)
    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Failed to delete mask %s: %s", path, exc)
