"""Scale calibration model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ScaleCalibration:
    """Manual or automatic scale bar calibration for one image."""

    start_point: list[float]  # [x, y] image pixels
    end_point: list[float]
    pixel_length: float
    real_length: float
    unit: str  # "um" | "mm" | "cm"
    real_per_pixel: float  # real_length / pixel_length (in ``unit``)
    method: str = "manual"  # manual | auto_pending
    confirmed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ScaleCalibration | None:
        if not data:
            return None
        return cls(
            start_point=[float(data["start_point"][0]), float(data["start_point"][1])],
            end_point=[float(data["end_point"][0]), float(data["end_point"][1])],
            pixel_length=float(data["pixel_length"]),
            real_length=float(data["real_length"]),
            unit=str(data.get("unit", "um")),
            real_per_pixel=float(data["real_per_pixel"]),
            method=str(data.get("method", "manual")),
            confirmed=bool(data.get("confirmed", True)),
        )
