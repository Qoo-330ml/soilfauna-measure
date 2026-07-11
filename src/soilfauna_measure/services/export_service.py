"""Orchestrate project export to exports/ folder."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from soilfauna_measure.exporters.image_export import (
    export_annotated_for_image,
    export_crops_for_image,
    export_masks_for_image,
)
from soilfauna_measure.exporters.table_export import export_csv, export_xlsx
from soilfauna_measure.models.project import Project
from soilfauna_measure.storage.workspace import Workspace

logger = logging.getLogger(__name__)


@dataclass
class ExportOptions:
    csv: bool = True
    xlsx: bool = True
    masks: bool = True
    crops: bool = True
    annotated: bool = True
    only_current_image: bool = False


@dataclass
class ExportResult:
    output_dir: Path
    files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def export_project(
    workspace: Workspace,
    options: ExportOptions | None = None,
    *,
    current_image_id: str | None = None,
) -> ExportResult:
    """Export tables and images under workspace/exports/<timestamp>/."""
    options = options or ExportOptions()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = workspace.root / "exports" / stamp
    out.mkdir(parents=True, exist_ok=True)
    result = ExportResult(output_dir=out)
    project: Project = workspace.project

    try:
        if options.csv:
            p = export_csv(project, out / "measurements.csv")
            result.files.append(p)
        if options.xlsx:
            p = export_xlsx(project, out / "measurements.xlsx")
            result.files.append(p)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Table export failed")
        result.errors.append(f"表格导出失败: {exc}")

    images = project.images
    if options.only_current_image and current_image_id:
        images = [i for i in images if i.image_id == current_image_id]

    for img in images:
        if not img.objects and not (options.annotated):
            continue
        try:
            abs_path = workspace.abs_path(img)
            if not abs_path.is_file():
                result.errors.append(f"图片缺失: {img.relative_path}")
                continue
            if options.masks and img.objects:
                mask_dir = out / "masks" / img.image_id
                result.files.extend(
                    export_masks_for_image(workspace.root, img, mask_dir)
                )
            if options.crops and img.objects:
                crop_dir = out / "crops" / img.image_id
                result.files.extend(
                    export_crops_for_image(workspace.root, img, abs_path, crop_dir)
                )
            if options.annotated:
                ann = out / "annotated" / f"{img.image_id}_annotated.png"
                result.files.append(
                    export_annotated_for_image(
                        workspace.root,
                        img,
                        abs_path,
                        project.categories,
                        ann,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Image export failed for %s", img.image_id)
            result.errors.append(f"{img.image_id}: {exc}")

    return result
