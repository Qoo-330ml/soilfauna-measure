"""Background batch tasks using QRunnable + signals."""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from soilfauna_measure.core.image_loader import load_image
from soilfauna_measure.core.segmentation import SegmentationParams, segment_instances
from soilfauna_measure.models.calibration import ScaleCalibration
from soilfauna_measure.models.image_record import ImageRecord
from soilfauna_measure.models.project import Project

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    progress = Signal(int, int, str)  # current, total, message
    item_finished = Signal(str, object)  # image_id, result payload
    error = Signal(str, str)  # image_id, error message
    finished = Signal(object)  # summary dict
    cancelled = Signal()


@dataclass
class BatchJobResult:
    image_id: str
    ok: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class _Cancellable:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class BatchSegmentRunnable(QRunnable):
    """Run auto-segmentation on multiple images offline (no Qt widgets).

    Does NOT write to project; returns instance masks as arrays for main thread
    to apply safely (so cancel doesn't half-write).
    """

    def __init__(
        self,
        items: list[tuple[str, Path]],  # image_id, abs path
        params: SegmentationParams,
        *,
        signals: WorkerSignals | None = None,
    ) -> None:
        super().__init__()
        self.items = items
        self.params = params
        self.signals = signals or WorkerSignals()
        self.control = _Cancellable()
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self.control.cancel()

    @Slot()
    def run(self) -> None:
        total = len(self.items)
        results: list[BatchJobResult] = []
        try:
            for i, (image_id, path) in enumerate(self.items):
                if self.control.is_cancelled:
                    self.signals.cancelled.emit()
                    self.signals.finished.emit(
                        {
                            "cancelled": True,
                            "results": results,
                            "completed": len(results),
                            "total": total,
                        }
                    )
                    return
                self.signals.progress.emit(i + 1, total, f"分割 {image_id}")
                try:
                    loaded = load_image(path)
                    seg = segment_instances(loaded.raw, self.params)
                    # serialize lightweight: list of (area, contour, mask array)
                    instances = []
                    for inst in seg.instances:
                        instances.append(
                            {
                                "area_px": inst.area_px,
                                "contour": inst.contour,
                                "mask": inst.mask,
                            }
                        )
                    payload = {
                        "instances": instances,
                        "message": seg.message,
                        "width": loaded.meta.width,
                        "height": loaded.meta.height,
                        "channels": loaded.meta.channels,
                        "dtype": loaded.meta.dtype,
                    }
                    jr = BatchJobResult(image_id, True, seg.message, payload)
                    results.append(jr)
                    self.signals.item_finished.emit(image_id, payload)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Batch segment failed %s", image_id)
                    msg = str(exc)
                    results.append(BatchJobResult(image_id, False, msg))
                    self.signals.error.emit(image_id, msg)

            self.signals.finished.emit(
                {
                    "cancelled": False,
                    "results": results,
                    "completed": len(results),
                    "total": total,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit("_batch_", f"{exc}\n{traceback.format_exc()}")
            self.signals.finished.emit(
                {
                    "cancelled": False,
                    "results": results,
                    "completed": len(results),
                    "total": total,
                    "fatal": str(exc),
                }
            )


class BatchScaleRunnable(QRunnable):
    """Apply the same ScaleCalibration dict to many image_ids (main thread apply).

    Worker only prepares the list; actual mutation happens on main thread via signal
    for thread safety of Project model. Here we just iterate and emit apply requests.
    """

    def __init__(
        self,
        image_ids: list[str],
        scale: ScaleCalibration,
        *,
        signals: WorkerSignals | None = None,
        skip_confirmed_scale: bool = True,
    ) -> None:
        super().__init__()
        self.image_ids = image_ids
        self.scale = scale
        self.signals = signals or WorkerSignals()
        self.control = _Cancellable()
        self.skip_confirmed_scale = skip_confirmed_scale
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self.control.cancel()

    @Slot()
    def run(self) -> None:
        total = len(self.image_ids)
        results: list[BatchJobResult] = []
        for i, iid in enumerate(self.image_ids):
            if self.control.is_cancelled:
                self.signals.cancelled.emit()
                self.signals.finished.emit(
                    {
                        "cancelled": True,
                        "results": results,
                        "completed": len(results),
                        "total": total,
                    }
                )
                return
            self.signals.progress.emit(i + 1, total, f"比例尺 {iid}")
            # Emit scale to apply on main thread
            payload = {"scale": self.scale, "skip_if_confirmed": self.skip_confirmed_scale}
            results.append(BatchJobResult(iid, True, "ok", payload))
            self.signals.item_finished.emit(iid, payload)
        self.signals.finished.emit(
            {
                "cancelled": False,
                "results": results,
                "completed": len(results),
                "total": total,
            }
        )


class BatchPathRunnable(QRunnable):
    """Suggest length paths for objects given mask arrays."""

    def __init__(
        self,
        tasks: list[tuple[str, str, Any]],  # image_id, object_id, mask
        *,
        signals: WorkerSignals | None = None,
        min_branch_length: float = 10.0,
        target_nodes: int = 8,
    ) -> None:
        super().__init__()
        self.tasks = tasks
        self.signals = signals or WorkerSignals()
        self.control = _Cancellable()
        self.min_branch_length = min_branch_length
        self.target_nodes = target_nodes
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self.control.cancel()

    @Slot()
    def run(self) -> None:
        from soilfauna_measure.core.skeleton import (
            PathSuggestionError,
            suggest_length_path,
        )

        total = len(self.tasks)
        results: list[BatchJobResult] = []
        for i, (image_id, object_id, mask) in enumerate(self.tasks):
            if self.control.is_cancelled:
                self.signals.cancelled.emit()
                self.signals.finished.emit(
                    {
                        "cancelled": True,
                        "results": results,
                        "completed": len(results),
                        "total": total,
                    }
                )
                return
            self.signals.progress.emit(
                i + 1, total, f"体长建议 {object_id}"
            )
            try:
                sug = suggest_length_path(
                    mask,
                    min_branch_length=self.min_branch_length,
                    target_nodes=self.target_nodes,
                )
                payload = {
                    "object_id": object_id,
                    "image_id": image_id,
                    "points": sug.points,
                    "length_px": sug.length_px,
                    "message": sug.message,
                }
                results.append(BatchJobResult(object_id, True, sug.message, payload))
                self.signals.item_finished.emit(object_id, payload)
            except PathSuggestionError as exc:
                results.append(BatchJobResult(object_id, False, str(exc)))
                self.signals.error.emit(object_id, str(exc))
            except Exception as exc:  # noqa: BLE001
                results.append(BatchJobResult(object_id, False, str(exc)))
                self.signals.error.emit(object_id, str(exc))
        self.signals.finished.emit(
            {
                "cancelled": False,
                "results": results,
                "completed": len(results),
                "total": total,
            }
        )


class BatchController(QObject):
    """Owns thread pool and active runnable cancel handle."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self._active: BatchSegmentRunnable | BatchScaleRunnable | BatchPathRunnable | None = None
        self.signals = WorkerSignals()

    @property
    def is_busy(self) -> bool:
        return self._active is not None

    def cancel(self) -> None:
        if self._active is not None:
            self._active.cancel()

    def start_segment(
        self,
        items: list[tuple[str, Path]],
        params: SegmentationParams,
    ) -> WorkerSignals:
        if self._active is not None:
            raise RuntimeError("已有批处理在运行")
        sig = WorkerSignals()
        run = BatchSegmentRunnable(items, params, signals=sig)
        self._active = run

        def _clear(*_a: Any) -> None:
            self._active = None

        sig.finished.connect(_clear)
        self.pool.start(run)
        return sig

    def start_scale(
        self,
        image_ids: list[str],
        scale: ScaleCalibration,
        *,
        skip_confirmed_scale: bool = True,
    ) -> WorkerSignals:
        if self._active is not None:
            raise RuntimeError("已有批处理在运行")
        sig = WorkerSignals()
        run = BatchScaleRunnable(
            image_ids, scale, signals=sig, skip_confirmed_scale=skip_confirmed_scale
        )
        self._active = run

        def _clear(*_a: Any) -> None:
            self._active = None

        sig.finished.connect(_clear)
        self.pool.start(run)
        return sig

    def start_paths(
        self,
        tasks: list[tuple[str, str, Any]],
        **kwargs: Any,
    ) -> WorkerSignals:
        if self._active is not None:
            raise RuntimeError("已有批处理在运行")
        sig = WorkerSignals()
        run = BatchPathRunnable(tasks, signals=sig, **kwargs)
        self._active = run

        def _clear(*_a: Any) -> None:
            self._active = None

        sig.finished.connect(_clear)
        self.pool.start(run)
        return sig
