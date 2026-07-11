"""CSV / Excel measurement table export."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from soilfauna_measure.models.category import Category
from soilfauna_measure.models.project import Project


def _category_map(project: Project) -> dict[str, Category]:
    return {c.category_id: c for c in project.categories}


def build_measurement_rows(project: Project) -> list[dict[str, Any]]:
    """One row per specimen object across all images."""
    cats = _category_map(project)
    rows: list[dict[str, Any]] = []
    for img in project.images:
        scale = img.scale
        for obj in img.objects:
            cat = cats.get(obj.category_id)
            rows.append(
                {
                    "project": project.project_name,
                    "image_id": img.image_id,
                    "image_file": Path(img.relative_path).name,
                    "object_id": obj.object_id,
                    "category_id": obj.category_id,
                    "category_zh": cat.name_zh if cat else obj.category_id,
                    "category_en": cat.name_en if cat else "",
                    "area_px": obj.area_px,
                    "area_um2": obj.area_um2 if obj.area_um2 is not None else "",
                    "area_mm2": obj.area_mm2 if obj.area_mm2 is not None else "",
                    "length_px": obj.length_px if obj.length_px is not None else "",
                    "length_um": obj.length_um if obj.length_um is not None else "",
                    "length_mm": obj.length_mm if obj.length_mm is not None else "",
                    "length_nodes": len(obj.length_points or []),
                    "length_source": obj.length_source,
                    "measurement_scope": obj.measurement_scope,
                    "segmentation_method": obj.segmentation_method,
                    "confirmed": obj.confirmed,
                    "overlap_status": obj.overlap_status,
                    "notes": obj.notes,
                    "mask_path": obj.mask_path,
                    "image_width": img.width,
                    "image_height": img.height,
                    "scale_unit": scale.unit if scale else "",
                    "scale_real_per_pixel": scale.real_per_pixel if scale else "",
                    "scale_confirmed": scale.confirmed if scale else "",
                    "image_status": img.status,
                }
            )
    return rows


COLUMN_ORDER = [
    "project",
    "image_id",
    "image_file",
    "object_id",
    "category_id",
    "category_zh",
    "category_en",
    "area_px",
    "area_um2",
    "area_mm2",
    "length_px",
    "length_um",
    "length_mm",
    "length_nodes",
    "length_source",
    "measurement_scope",
    "segmentation_method",
    "confirmed",
    "overlap_status",
    "notes",
    "mask_path",
    "image_width",
    "image_height",
    "scale_unit",
    "scale_real_per_pixel",
    "scale_confirmed",
    "image_status",
]


def export_csv(project: Project, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_measurement_rows(project)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMN_ORDER, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def export_xlsx(project: Project, path: Path | str) -> Path:
    """Write Excel via openpyxl only (no pandas — keeps install/package smaller)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_measurement_rows(project)
    return _export_xlsx_openpyxl(rows, path)


def _export_xlsx_openpyxl(rows: list[dict[str, Any]], path: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "measurements"
    ws.append(COLUMN_ORDER)
    for row in rows:
        ws.append([row.get(c, "") for c in COLUMN_ORDER])
    wb.save(path)
    return path
