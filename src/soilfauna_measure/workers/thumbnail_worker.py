"""Background thumbnail generation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from soilfauna_measure.services.thumbnail_service import ensure_thumbnail


class ThumbnailSignals(QObject):
    ready = Signal(str, str)  # image_id, thumb_path
    finished = Signal()


class ThumbnailBatchRunnable(QRunnable):
    def __init__(
        self,
        workspace_root: Path,
        items: list[tuple[str, Path]],  # image_id, abs path
        *,
        signals: ThumbnailSignals | None = None,
    ) -> None:
        super().__init__()
        self.workspace_root = Path(workspace_root)
        self.items = items
        self.signals = signals or ThumbnailSignals()
        self._cancelled = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        for image_id, src in self.items:
            if self._cancelled:
                break
            if not src.is_file():
                continue
            thumb = ensure_thumbnail(self.workspace_root, src, image_stem=image_id)
            if thumb is not None:
                self.signals.ready.emit(image_id, str(thumb))
        self.signals.finished.emit()


def start_thumbnail_batch(
    workspace_root: Path,
    items: list[tuple[str, Path]],
) -> tuple[ThumbnailSignals, ThumbnailBatchRunnable]:
    sig = ThumbnailSignals()
    run = ThumbnailBatchRunnable(workspace_root, items, signals=sig)
    QThreadPool.globalInstance().start(run)
    return sig, run
