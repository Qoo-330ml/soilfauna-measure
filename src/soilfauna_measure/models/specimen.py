"""Specimen object model (schema-ready for M3+; unused in UI for M2)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SpecimenObject:
    object_id: str
    category_id: str = "unclassified"
    mask_path: str = ""
    contour: list[list[float]] = field(default_factory=list)
    length_points: list[list[float]] = field(default_factory=list)
    length_source: str = "none"  # none | manual | auto_suggested
    area_px: float = 0.0
    area_um2: float | None = None
    area_mm2: float | None = None
    length_px: float | None = None
    length_um: float | None = None
    length_mm: float | None = None
    measurement_scope: str = "whole"
    segmentation_method: str = "manual"
    confirmed: bool = False
    overlap_status: str = "none"
    notes: str = ""
    extra_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpecimenObject:
        return cls(
            object_id=str(data["object_id"]),
            category_id=str(data.get("category_id", "unclassified")),
            mask_path=str(data.get("mask_path", "")),
            contour=list(data.get("contour") or []),
            length_points=list(data.get("length_points") or []),
            length_source=str(data.get("length_source", "none")),
            area_px=float(data.get("area_px", 0.0)),
            area_um2=_opt_float(data.get("area_um2")),
            area_mm2=_opt_float(data.get("area_mm2")),
            length_px=_opt_float(data.get("length_px")),
            length_um=_opt_float(data.get("length_um")),
            length_mm=_opt_float(data.get("length_mm")),
            measurement_scope=str(data.get("measurement_scope", "whole")),
            segmentation_method=str(data.get("segmentation_method", "manual")),
            confirmed=bool(data.get("confirmed", False)),
            overlap_status=str(data.get("overlap_status", "none")),
            notes=str(data.get("notes", "")),
            extra_metrics=dict(data.get("extra_metrics") or {}),
        )


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    return float(v)
