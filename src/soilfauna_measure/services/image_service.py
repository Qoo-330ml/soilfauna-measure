"""Image loading cache for the UI layer."""

from __future__ import annotations

import logging
from pathlib import Path

from soilfauna_measure.core.image_loader import (
    ImageLoadError,
    LoadedImage,
    load_image,
)

logger = logging.getLogger(__name__)


class ImageService:
    """Simple single-slot cache for the currently displayed image."""

    def __init__(self) -> None:
        self._cache_path: Path | None = None
        self._cache: LoadedImage | None = None

    def clear(self) -> None:
        self._cache_path = None
        self._cache = None

    def get(self, path: Path | str) -> LoadedImage:
        path = Path(path).resolve()
        if self._cache is not None and self._cache_path == path:
            return self._cache
        logger.info("Loading image: %s", path)
        loaded = load_image(path)
        self._cache_path = path
        self._cache = loaded
        return loaded

    def try_get(self, path: Path | str) -> tuple[LoadedImage | None, str | None]:
        """Return (loaded, None) or (None, error_message)."""
        try:
            return self.get(path), None
        except ImageLoadError as exc:
            logger.exception("Image load failed: %s", path)
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected image load error: %s", path)
            return None, f"Unexpected error: {exc}"
