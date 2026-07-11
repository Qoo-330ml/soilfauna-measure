"""Specimen object creation, mask cache, and metrics."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np

from soilfauna_measure.core.calibration import area_px_to_real
from soilfauna_measure.core.measurement import (
    apply_length_to_object,
    copy_points,
    longest_length_run,
    polyline_length_px,
    split_length_path_by_mask,
)
from soilfauna_measure.core.mask_operations import (
    apply_brush_stroke,
    connected_mask_parts,
    empty_mask,
    ensure_binary_mask,
    mask_area_px,
    mask_to_contour,
    point_in_mask,
    polygon_to_mask,
    split_mask_by_polylines,
)
from soilfauna_measure.core.segmentation import (
    SegmentationError,
    SegmentationParams,
    SegmentationResult,
    merge_masks,
    segment_instances,
    split_mask_by_cut_line,
    split_mask_by_seeds,
)
from soilfauna_measure.models.calibration import ScaleCalibration
from soilfauna_measure.models.image_record import ImageRecord
from soilfauna_measure.models.specimen import SpecimenObject
from soilfauna_measure.storage.mask_store import (
    MaskStoreError,
    delete_mask,
    load_mask,
    mask_relative_path,
    save_mask,
)

logger = logging.getLogger(__name__)


class ObjectService:
    """Manages per-image object masks in memory + disk."""

    def __init__(self) -> None:
        self._workspace_root: Path | None = None
        self._image_id: str | None = None
        self._height = 0
        self._width = 0
        # object_id -> uint8 mask
        self._masks: dict[str, np.ndarray] = {}

    def clear(self) -> None:
        self._masks.clear()
        self._image_id = None
        self._height = 0
        self._width = 0

    def set_workspace(self, root: Path | None) -> None:
        self._workspace_root = root
        self.clear()

    def bind_image(
        self,
        record: ImageRecord,
        *,
        width: int,
        height: int,
    ) -> None:
        """Load masks for an image record into cache."""
        self._image_id = record.image_id
        self._width = int(width)
        self._height = int(height)
        self._masks.clear()
        if self._workspace_root is None:
            return
        shape = (self._height, self._width)
        for obj in record.objects:
            try:
                if obj.mask_path:
                    m = load_mask(
                        self._workspace_root,
                        obj.mask_path,
                        expected_shape=shape,
                    )
                else:
                    m = empty_mask(self._height, self._width)
                self._masks[obj.object_id] = m
            except MaskStoreError:
                logger.warning("Missing mask for %s", obj.object_id)
                self._masks[obj.object_id] = empty_mask(self._height, self._width)

    def get_mask(self, object_id: str) -> np.ndarray | None:
        return self._masks.get(object_id)

    def allocate_object_id(self, record: ImageRecord) -> str:
        seq = max(int(record.next_object_seq), 1)
        oid = f"{record.image_id}_{seq:03d}"
        # ensure unique even if seq drifted
        existing = {o.object_id for o in record.objects}
        while oid in existing:
            seq += 1
            oid = f"{record.image_id}_{seq:03d}"
        record.next_object_seq = seq + 1
        return oid

    def refresh_metrics(
        self,
        obj: SpecimenObject,
        scale: ScaleCalibration | None,
        *,
        contour_from_mask: bool = True,
        contour_override: list[list[float]] | None = None,
    ) -> None:
        mask = self._masks.get(obj.object_id)
        area = mask_area_px(mask)
        obj.area_px = float(area)
        obj.area_um2 = area_px_to_real(area, scale, "um")
        obj.area_mm2 = area_px_to_real(area, scale, "mm")
        if contour_override is not None:
            obj.contour = contour_override
        elif contour_from_mask and mask is not None:
            obj.contour = mask_to_contour(mask)

    def create_from_polygon(
        self,
        record: ImageRecord,
        points: Sequence[Sequence[float]],
        scale: ScaleCalibration | None,
        *,
        category_id: str = "unclassified",
    ) -> SpecimenObject:
        if self._workspace_root is None:
            raise RuntimeError("Workspace not set")
        if len(points) < 3:
            raise ValueError("Polygon needs at least 3 points")
        if self._width <= 0 or self._height <= 0:
            raise ValueError("Image size unknown")

        mask = polygon_to_mask(points, self._height, self._width)
        if mask_area_px(mask) == 0:
            raise ValueError("Polygon produced empty mask")
        contour = [[float(p[0]), float(p[1])] for p in points]
        return self.create_from_mask(
            record,
            mask,
            scale,
            category_id=category_id,
            segmentation_method="manual",
            contour=contour,
            confirmed=False,
        )

    def create_from_mask(
        self,
        record: ImageRecord,
        mask: np.ndarray,
        scale: ScaleCalibration | None,
        *,
        category_id: str = "unclassified",
        segmentation_method: str = "manual",
        contour: list[list[float]] | None = None,
        confirmed: bool = False,
        notes: str = "",
    ) -> SpecimenObject:
        if self._workspace_root is None:
            raise RuntimeError("Workspace not set")
        if self._width <= 0 or self._height <= 0:
            raise ValueError("Image size unknown")
        mask = ensure_binary_mask(mask)
        if mask.shape != (self._height, self._width):
            raise ValueError(
                f"Mask shape {mask.shape} != image ({self._height}, {self._width})"
            )
        if mask_area_px(mask) == 0:
            raise ValueError("Empty mask")

        oid = self.allocate_object_id(record)
        rel = save_mask(self._workspace_root, oid, mask)
        self._masks[oid] = mask
        obj = SpecimenObject(
            object_id=oid,
            category_id=category_id,
            mask_path=rel,
            contour=contour or [],
            segmentation_method=segmentation_method,
            measurement_scope="whole",
            confirmed=confirmed,
            notes=notes,
        )
        self.refresh_metrics(
            obj,
            scale,
            contour_from_mask=contour is None,
            contour_override=contour,
        )
        record.objects.append(obj)
        if record.status == "pending":
            record.status = "in_progress"
        if not confirmed and record.status not in ("needs_review", "done"):
            record.status = "needs_review"
        return obj

    def delete_object(self, record: ImageRecord, object_id: str) -> bool:
        idx = next((i for i, o in enumerate(record.objects) if o.object_id == object_id), None)
        if idx is None:
            return False
        record.objects.pop(idx)
        self._masks.pop(object_id, None)
        if self._workspace_root is not None:
            delete_mask(self._workspace_root, object_id)
        return True

    def paint_brush(
        self,
        record: ImageRecord,
        object_id: str,
        stroke_points: Sequence[Sequence[float]],
        radius: float,
        *,
        erase: bool = False,
        scale: ScaleCalibration | None = None,
        min_part_area: int = 30,
    ) -> SpecimenObject | list[SpecimenObject] | None:
        """Paint or erase along a stroke.

        On erase the result is always a list when the object is removed or
        split into independent objects; a single SpecimenObject if it stays one.

        - Empty mask → delete object, return ``[]``
        - Mask becomes ≥2 components (4-connected) → ≥2 independent objects
        - Length path severed into ≥2 runs while mask still bridges → still
          split into independent objects by nearest-run partition
        - Single remaining body → clip length to surviving path
        """
        obj = next((o for o in record.objects if o.object_id == object_id), None)
        if obj is None:
            return None
        mask = self._masks.get(object_id)
        if mask is None:
            mask = empty_mask(self._height, self._width)
            self._masks[object_id] = mask
        apply_brush_stroke(mask, stroke_points, radius, value=0 if erase else 255)
        self._masks[object_id] = ensure_binary_mask(mask)
        if self._workspace_root is not None:
            obj.mask_path = save_mask(
                self._workspace_root, object_id, self._masks[object_id]
            )
        self.refresh_metrics(obj, scale, contour_from_mask=True)
        obj.segmentation_method = (
            "manual"
            if obj.segmentation_method == "manual"
            else "automatic_then_manual"
        )

        if not erase:
            return obj

        return self._finalize_after_erase(
            record,
            object_id,
            scale,
            min_part_area=min_part_area,
        )

    def _finalize_after_erase(
        self,
        record: ImageRecord,
        object_id: str,
        scale: ScaleCalibration | None,
        *,
        min_part_area: int = 30,
    ) -> SpecimenObject | list[SpecimenObject]:
        """After erase: produce independent objects for each severed region."""
        obj = next((o for o in record.objects if o.object_id == object_id), None)
        if obj is None:
            return []
        mask = self._masks.get(object_id)
        if mask is None or mask_area_px(mask) == 0:
            self.delete_object(record, object_id)
            return []

        length_before = copy_points(obj.length_points)
        length_source = obj.length_source or "manual"
        cat = obj.category_id
        method = (
            "manual"
            if obj.segmentation_method == "manual"
            else "automatic_then_manual"
        )
        notes_base = (obj.notes or "").strip()
        # Dynamic dust threshold: keep small but real fragments
        area0 = max(mask_area_px(mask), 1)
        min_area = max(int(min_part_area), min(80, max(15, area0 // 40)))

        # 1) Topology: 4-connected parts (erase gap breaks diagonal glue)
        parts = connected_mask_parts(
            mask, min_area=min_area, connectivity=1
        )

        # Length runs surviving on remaining FG
        runs = (
            split_length_path_by_mask(length_before, mask, margin=2)
            if length_before
            else []
        )

        # 2) If mask still one piece but body-length is clearly two pieces,
        #    force a geometric partition so user gets two independent objects.
        if len(parts) <= 1 and len(runs) >= 2:
            forced = split_mask_by_polylines(mask, runs, min_area=min_area)
            if len(forced) >= 2:
                parts = forced

        if not parts:
            self.delete_object(record, object_id)
            return []

        if len(parts) == 1:
            self._masks[object_id] = parts[0]
            if self._workspace_root is not None:
                obj.mask_path = save_mask(
                    self._workspace_root, object_id, parts[0]
                )
            self.refresh_metrics(obj, scale, contour_from_mask=True)
            if runs:
                best = longest_length_run(runs)
                self.apply_length_points(
                    obj,
                    best if best else [],
                    scale,
                    source=length_source if best else "none",
                )
            elif length_before:
                self.apply_length_points(obj, [], scale, source="none")
            return obj

        # ≥2 independent regions → delete original, create one object each
        return self._spawn_objects_from_parts(
            record,
            parts,
            scale,
            source_object_id=object_id,
            category_id=cat,
            segmentation_method=method,
            notes_base=notes_base,
            length_runs=runs,
            length_source=length_source,
        )

    def _spawn_objects_from_parts(
        self,
        record: ImageRecord,
        parts: Sequence[np.ndarray],
        scale: ScaleCalibration | None,
        *,
        source_object_id: str,
        category_id: str,
        segmentation_method: str,
        notes_base: str,
        length_runs: Sequence[Sequence[Sequence[float]]],
        length_source: str,
    ) -> list[SpecimenObject]:
        """Replace ``source_object_id`` with one new object per mask part."""
        if source_object_id:
            self.delete_object(record, source_object_id)

        created: list[SpecimenObject] = []
        used_run_idx: set[int] = set()
        note = f"erase-split from {source_object_id}"
        if notes_base:
            note = f"{notes_base} | {note}"

        for part in parts:
            if mask_area_px(part) <= 0:
                continue
            new_obj = self.create_from_mask(
                record,
                part,
                scale,
                category_id=category_id,
                segmentation_method=segmentation_method,
                confirmed=False,
                notes=note,
            )
            # Best unused length run that still lies on this part
            best_i = -1
            best_l = -1.0
            best_piece: list[list[float]] = []
            for i, run in enumerate(length_runs):
                if i in used_run_idx:
                    continue
                on_part = split_length_path_by_mask(run, part, margin=3)
                piece = longest_length_run(on_part)
                if not piece:
                    continue
                L = polyline_length_px(piece)
                if L > best_l:
                    best_l = L
                    best_i = i
                    best_piece = piece
            if best_i >= 0 and best_piece:
                used_run_idx.add(best_i)
                self.apply_length_points(
                    new_obj, best_piece, scale, source=length_source
                )
            created.append(new_obj)

        logger.info(
            "Erase-split %s → %d independent object(s): %s",
            source_object_id,
            len(created),
            [o.object_id for o in created],
        )
        return created

    def hit_test(self, x: float, y: float, record: ImageRecord) -> str | None:
        """Return top-most (last in list) object_id under point."""
        for obj in reversed(record.objects):
            mask = self._masks.get(obj.object_id)
            if mask is not None and point_in_mask(mask, x, y):
                return obj.object_id
        return None

    def recompute_all_areas(
        self,
        record: ImageRecord,
        scale: ScaleCalibration | None,
    ) -> None:
        for obj in record.objects:
            self.refresh_metrics(obj, scale, contour_from_mask=False)

    def apply_length_points(
        self,
        obj: SpecimenObject,
        points: Sequence[Sequence[float]],
        scale: ScaleCalibration | None,
        *,
        source: str | None = None,
    ) -> None:
        """Write length_points and derived metrics onto the object."""
        fields = apply_length_to_object(points, scale)
        obj.length_points = fields["length_points"]
        obj.length_px = fields["length_px"]
        obj.length_um = fields["length_um"]
        obj.length_mm = fields["length_mm"]
        if source is not None:
            obj.length_source = source
        else:
            obj.length_source = fields["length_source"]

    def apply_instance_masks(
        self,
        record: ImageRecord,
        instances: Sequence[dict],
        scale: ScaleCalibration | None,
        *,
        mode: str = "replace_unconfirmed",
        segmentation_method: str = "automatic",
        auto_length: bool = True,
    ) -> list[SpecimenObject]:
        """Apply precomputed instance dicts {mask, contour?, area_px?} from batch worker.

        Same confirmed-object protection as apply_auto_segmentation.
        If auto_length is True, skeleton body-length is suggested for each new object.
        """
        if mode == "replace_all":
            if any(o.confirmed for o in record.objects):
                raise ValueError("存在已确认对象，拒绝 replace_all")
            for oid in [o.object_id for o in list(record.objects)]:
                self.delete_object(record, oid)
        elif mode == "replace_unconfirmed":
            for oid in [o.object_id for o in list(record.objects) if not o.confirmed]:
                self.delete_object(record, oid)
        elif mode == "append":
            pass
        else:
            raise ValueError(f"Unknown mode: {mode}")

        created: list[SpecimenObject] = []
        for inst in instances:
            mask = inst.get("mask")
            if mask is None:
                continue
            try:
                obj = self.create_from_mask(
                    record,
                    mask,
                    scale,
                    category_id="unclassified",
                    segmentation_method=segmentation_method,
                    contour=inst.get("contour"),
                    confirmed=False,
                    notes="auto-segmented; pending review",
                )
                if auto_length:
                    self._try_auto_length(obj, scale)
                created.append(obj)
            except ValueError:
                logger.warning("Skipped invalid instance")
        record.status = "needs_review"
        return created

    def _try_auto_length(
        self,
        obj: SpecimenObject,
        scale: ScaleCalibration | None,
        *,
        min_branch_length: float = 10.0,
        target_nodes: int = 8,
    ) -> bool:
        """Best-effort auto length; never fails the parent segmentation."""
        try:
            self.suggest_length_for_object(
                obj,
                scale,
                min_branch_length=min_branch_length,
                target_nodes=target_nodes,
                overwrite_manual=True,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.info("Auto length skipped for %s: %s", obj.object_id, exc)
            return False

    def suggest_length_for_object(
        self,
        obj: SpecimenObject,
        scale: ScaleCalibration | None,
        *,
        min_branch_length: float = 10.0,
        target_nodes: int = 8,
        overwrite_manual: bool = False,
    ) -> SpecimenObject:
        """Auto-suggest length path from mask; marks length_source=auto_suggested.

        Refuses to overwrite length_source=manual unless overwrite_manual=True.
        """
        from soilfauna_measure.core.skeleton import (
            PathSuggestionError,
            suggest_length_path,
        )

        if (
            obj.length_points
            and obj.length_source == "manual"
            and not overwrite_manual
        ):
            raise ValueError("已有人工体长路径；请先清空或勾选覆盖")
        mask = self._masks.get(obj.object_id)
        if mask is None:
            raise ValueError("掩膜缺失")
        try:
            sug = suggest_length_path(
                mask,
                min_branch_length=min_branch_length,
                target_nodes=target_nodes,
            )
        except PathSuggestionError as exc:
            raise ValueError(str(exc)) from exc
        self.apply_length_points(
            obj, sug.points, scale, source="auto_suggested"
        )
        note = sug.message
        if obj.notes and note not in obj.notes:
            obj.notes = (obj.notes + "; " + note).strip("; ")
        elif not obj.notes:
            obj.notes = note
        return obj

    def recompute_all_lengths(
        self,
        record: ImageRecord,
        scale: ScaleCalibration | None,
    ) -> None:
        for obj in record.objects:
            if obj.length_points:
                src = obj.length_source or "manual"
                self.apply_length_points(obj, obj.length_points, scale, source=src)

    def recompute_all_metrics(
        self,
        record: ImageRecord,
        scale: ScaleCalibration | None,
    ) -> None:
        self.recompute_all_areas(record, scale)
        self.recompute_all_lengths(record, scale)

    def persist_all_dirty_masks(self, record: ImageRecord) -> None:
        """Ensure all cached masks are written (e.g. before project save)."""
        if self._workspace_root is None:
            return
        for obj in record.objects:
            mask = self._masks.get(obj.object_id)
            if mask is None:
                continue
            obj.mask_path = save_mask(self._workspace_root, obj.object_id, mask)

    def apply_auto_segmentation(
        self,
        record: ImageRecord,
        image: np.ndarray,
        scale: ScaleCalibration | None,
        params: SegmentationParams | None = None,
        *,
        mode: str = "replace_unconfirmed",
        auto_length: bool = True,
    ) -> tuple[list[SpecimenObject], SegmentationResult]:
        """Run auto segmentation and create objects.

        Modes:
        - replace_unconfirmed: delete unconfirmed objects, keep confirmed, add new
        - append: only add new instances, keep all existing
        - replace_all: refuse if any confirmed; else clear all and add

        Never deletes confirmed objects.

        When auto_length is True (default), each new instance also gets a skeleton
        body-length suggestion marked as auto_suggested (editable, needs review).
        """
        params = params or SegmentationParams.preset_whole()
        result = segment_instances(image, params)

        if mode == "replace_all":
            if any(o.confirmed for o in record.objects):
                raise ValueError(
                    "存在已确认对象，拒绝 replace_all。请改用 replace_unconfirmed 或 append。"
                )
            for oid in [o.object_id for o in list(record.objects)]:
                self.delete_object(record, oid)
        elif mode == "replace_unconfirmed":
            for oid in [o.object_id for o in list(record.objects) if not o.confirmed]:
                self.delete_object(record, oid)
        elif mode == "append":
            pass
        else:
            raise ValueError(f"Unknown mode: {mode}")

        created: list[SpecimenObject] = []
        n_with_length = 0
        for inst in result.instances:
            try:
                obj = self.create_from_mask(
                    record,
                    inst.mask,
                    scale,
                    category_id="unclassified",
                    segmentation_method="automatic",
                    contour=inst.contour or None,
                    confirmed=False,
                    notes="auto-segmented; pending review",
                )
                if auto_length and self._try_auto_length(obj, scale):
                    n_with_length += 1
                created.append(obj)
            except ValueError:
                logger.warning("Skipped empty/invalid instance label=%s", inst.label)
        record.status = "needs_review"
        if auto_length and created:
            result.message = (
                f"{result.message}；其中 {n_with_length}/{len(created)} 个已生成体长建议"
            )
        return created, result

    def merge_objects(
        self,
        record: ImageRecord,
        object_ids: Sequence[str],
        scale: ScaleCalibration | None,
    ) -> SpecimenObject:
        """Merge two or more objects into one new object; delete sources."""
        if len(object_ids) < 2:
            raise ValueError("合并至少需要 2 个对象")
        masks = []
        sources = []
        for oid in object_ids:
            obj = next((o for o in record.objects if o.object_id == oid), None)
            if obj is None:
                raise ValueError(f"对象不存在: {oid}")
            if obj.confirmed:
                raise ValueError(f"不能合并已确认对象: {oid}")
            m = self._masks.get(oid)
            if m is None:
                raise ValueError(f"掩膜缺失: {oid}")
            masks.append(m)
            sources.append(obj)

        merged = merge_masks(masks)
        # delete sources first (ids not reused)
        for oid in object_ids:
            self.delete_object(record, oid)

        new_obj = self.create_from_mask(
            record,
            merged,
            scale,
            category_id=sources[0].category_id,
            segmentation_method="automatic_then_manual",
            confirmed=False,
            notes=f"merged from {', '.join(object_ids)}",
        )
        return new_obj

    def split_object_by_cut(
        self,
        record: ImageRecord,
        object_id: str,
        polyline: Sequence[Sequence[float]],
        scale: ScaleCalibration | None,
        *,
        line_width: int = 4,
        min_area: int = 80,
    ) -> list[SpecimenObject]:
        obj = next((o for o in record.objects if o.object_id == object_id), None)
        if obj is None:
            raise ValueError(f"对象不存在: {object_id}")
        if obj.confirmed:
            raise ValueError("不能拆分已确认对象")
        mask = self._masks.get(object_id)
        if mask is None:
            raise ValueError("掩膜缺失")
        parts = split_mask_by_cut_line(
            mask,
            [[float(p[0]), float(p[1])] for p in polyline],
            line_width=line_width,
            min_area=min_area,
        )
        if len(parts) < 2:
            raise ValueError("切割后未得到多个连通区域，请调整切割线")
        cat = obj.category_id
        self.delete_object(record, object_id)
        created: list[SpecimenObject] = []
        for part in parts:
            created.append(
                self.create_from_mask(
                    record,
                    part,
                    scale,
                    category_id=cat,
                    segmentation_method="automatic_then_manual",
                    confirmed=False,
                    notes=f"split from {object_id}",
                )
            )
        return created

    def split_object_by_seeds(
        self,
        record: ImageRecord,
        object_id: str,
        seeds: Sequence[tuple[float, float]],
        scale: ScaleCalibration | None,
        *,
        min_area: int = 80,
    ) -> list[SpecimenObject]:
        obj = next((o for o in record.objects if o.object_id == object_id), None)
        if obj is None:
            raise ValueError(f"对象不存在: {object_id}")
        if obj.confirmed:
            raise ValueError("不能拆分已确认对象")
        mask = self._masks.get(object_id)
        if mask is None:
            raise ValueError("掩膜缺失")
        if len(seeds) < 2:
            raise ValueError("至少需要 2 个种子点")
        parts = split_mask_by_seeds(
            mask,
            [(float(x), float(y)) for x, y in seeds],
            min_area=min_area,
        )
        if len(parts) < 2:
            raise ValueError("种子拆分未得到多个区域")
        cat = obj.category_id
        self.delete_object(record, object_id)
        created: list[SpecimenObject] = []
        for part in parts:
            created.append(
                self.create_from_mask(
                    record,
                    part,
                    scale,
                    category_id=cat,
                    segmentation_method="automatic_then_manual",
                    confirmed=False,
                    notes=f"seed-split from {object_id}",
                )
            )
        return created

    def set_confirmed(self, record: ImageRecord, object_id: str, confirmed: bool) -> None:
        obj = next((o for o in record.objects if o.object_id == object_id), None)
        if obj is None:
            return
        obj.confirmed = confirmed

