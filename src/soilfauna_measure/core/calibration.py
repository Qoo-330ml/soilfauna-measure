"""Scale calibration pure functions (no Qt)."""

from __future__ import annotations

from typing import Iterable

from soilfauna_measure.core.coordinate_utils import pixel_distance
from soilfauna_measure.models.calibration import ScaleCalibration

# Canonical internal length unit is micrometre (um).
UNIT_TO_UM = {
    "um": 1.0,
    "µm": 1.0,
    "μm": 1.0,  # Greek mu
    "micron": 1.0,
    "microns": 1.0,
    "mm": 1000.0,
    "cm": 10000.0,
    "m": 1_000_000.0,
}

UM_TO_UNIT = {
    "um": 1.0,
    "mm": 1.0 / 1000.0,
    "cm": 1.0 / 10000.0,
    "m": 1.0 / 1_000_000.0,
}

DISPLAY_UNIT_LABELS = {
    "um": "µm",
    "mm": "mm",
    "cm": "cm",
}


class CalibrationError(ValueError):
    """Invalid calibration inputs."""


def normalize_unit(unit: str) -> str:
    """Normalize unit string to one of: um, mm, cm."""
    u = (unit or "").strip().lower()
    # unify micro signs
    u = u.replace("μ", "u").replace("µ", "u")
    if u in {"u", "um", "umm", "micron", "microns", "micrometer", "micrometre"}:
        return "um"
    if u in {"mm", "millimeter", "millimetre"}:
        return "mm"
    if u in {"cm", "centimeter", "centimetre"}:
        return "cm"
    if u in UNIT_TO_UM:
        # map m etc. — keep as-is only if in DISPLAY
        if u == "m":
            return "m"
        return u
    raise CalibrationError(f"Unsupported unit: {unit!r}")


def unit_to_um(value: float, unit: str) -> float:
    """Convert a length value to micrometres."""
    key = normalize_unit(unit)
    if key not in UNIT_TO_UM:
        raise CalibrationError(f"Unsupported unit: {unit!r}")
    return float(value) * UNIT_TO_UM[key]


def um_to_unit(value_um: float, unit: str) -> float:
    """Convert micrometres to target unit."""
    key = normalize_unit(unit)
    if key not in UM_TO_UNIT and key not in UNIT_TO_UM:
        raise CalibrationError(f"Unsupported unit: {unit!r}")
    factor = UM_TO_UNIT.get(key)
    if factor is None:
        factor = 1.0 / UNIT_TO_UM[key]
    return float(value_um) * factor


def convert_length(value: float, from_unit: str, to_unit: str) -> float:
    """Convert length between units."""
    return um_to_unit(unit_to_um(value, from_unit), to_unit)


def compute_pixel_length(
    start: Iterable[float],
    end: Iterable[float],
) -> float:
    """Distance in pixels between two image points."""
    x0, y0 = start
    x1, y1 = end
    return pixel_distance(float(x0), float(y0), float(x1), float(y1))


def compute_real_per_pixel(real_length: float, pixel_length: float) -> float:
    """scale = real_length / pixel_length (same unit as real_length)."""
    if pixel_length <= 0:
        raise CalibrationError("pixel_length must be > 0")
    if real_length <= 0:
        raise CalibrationError("real_length must be > 0")
    return float(real_length) / float(pixel_length)


def build_scale_calibration(
    start_point: list[float] | tuple[float, float],
    end_point: list[float] | tuple[float, float],
    real_length: float,
    unit: str = "um",
    *,
    method: str = "manual",
    confirmed: bool = True,
) -> ScaleCalibration:
    """Create a ScaleCalibration from two points and a real length."""
    unit_n = normalize_unit(unit)
    if unit_n not in {"um", "mm", "cm"}:
        # For M2 UI we only store um/mm/cm
        if unit_n == "m":
            unit_n = "cm"
            real_length = real_length * 100.0
        else:
            raise CalibrationError(f"Unit not supported for storage: {unit}")

    px = compute_pixel_length(start_point, end_point)
    if px <= 0:
        raise CalibrationError("Scale bar endpoints must not be identical")
    rpp = compute_real_per_pixel(real_length, px)
    return ScaleCalibration(
        start_point=[float(start_point[0]), float(start_point[1])],
        end_point=[float(end_point[0]), float(end_point[1])],
        pixel_length=px,
        real_length=float(real_length),
        unit=unit_n,
        real_per_pixel=rpp,
        method=method,
        confirmed=confirmed,
    )


def real_per_pixel_um(scale: ScaleCalibration) -> float:
    """Return micrometres per pixel."""
    return unit_to_um(scale.real_per_pixel, scale.unit)


def length_px_to_real(
    length_px: float,
    scale: ScaleCalibration | None,
    out_unit: str = "um",
) -> float | None:
    """Convert pixel length to real units; None if no scale."""
    if scale is None:
        return None
    real_in_scale_unit = float(length_px) * scale.real_per_pixel
    return convert_length(real_in_scale_unit, scale.unit, out_unit)


def area_px_to_real(
    area_px: float,
    scale: ScaleCalibration | None,
    out_unit: str = "um",
) -> float | None:
    """Convert pixel area to real area (out_unit²); None if no scale.

    ``out_unit`` is a length unit; result is in out_unit squared.
    """
    if scale is None:
        return None
    # real_per_pixel in scale.unit → convert to out_unit first
    rpp_out = convert_length(scale.real_per_pixel, scale.unit, out_unit)
    return float(area_px) * (rpp_out ** 2)


def format_scale_summary(scale: ScaleCalibration | None) -> str:
    """Human-readable one-line scale summary for UI."""
    if scale is None:
        return "未校准"
    label = DISPLAY_UNIT_LABELS.get(scale.unit, scale.unit)
    conf = "已确认" if scale.confirmed else "待确认"
    return (
        f"{scale.real_per_pixel:.6g} {label}/px "
        f"({scale.real_length:g} {label} / {scale.pixel_length:.2f} px, {conf})"
    )
