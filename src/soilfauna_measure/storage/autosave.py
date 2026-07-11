"""Debounced autosave helper (Qt timer owned by UI)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from soilfauna_measure.models.project import Project
from soilfauna_measure.storage.project_io import save_autosave

logger = logging.getLogger(__name__)


class AutosaveController(QObject):
    """Debounce project autosaves to avoid writing on every mouse event."""

    def __init__(
        self,
        *,
        delay_ms: int = 2500,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._delay_ms = delay_ms
        self._workspace_root: Path | None = None
        self._project: Project | None = None
        self._get_project: Callable[[], Project | None] | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)
        self._enabled = True

    def set_workspace(
        self,
        root: Path | None,
        get_project: Callable[[], Project | None],
    ) -> None:
        self._workspace_root = root
        self._get_project = get_project
        self._timer.stop()

    def mark_dirty(self) -> None:
        """Schedule an autosave after idle delay."""
        if not self._enabled or self._workspace_root is None:
            return
        self._timer.start(self._delay_ms)

    def flush_now(self) -> bool:
        """Immediately write autosave if possible. Returns success."""
        self._timer.stop()
        return self._flush()

    def _flush(self) -> bool:
        if self._workspace_root is None or self._get_project is None:
            return False
        project = self._get_project()
        if project is None:
            return False
        try:
            save_autosave(project, self._workspace_root)
            logger.debug("Autosave written for %s", self._workspace_root)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Autosave failed")
            return False

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if not enabled:
            self._timer.stop()
