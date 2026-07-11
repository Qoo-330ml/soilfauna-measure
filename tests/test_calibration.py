"""Scale calibration pure function tests."""

import pytest

from soilfauna_measure.core.calibration import (
    CalibrationError,
    area_px_to_real,
    build_scale_calibration,
    compute_pixel_length,
    compute_real_per_pixel,
    convert_length,
    length_px_to_real,
    normalize_unit,
    real_per_pixel_um,
    unit_to_um,
    um_to_unit,
)


def test_normalize_unit_micro_signs():
    assert normalize_unit("µm") == "um"
    assert normalize_unit("μm") == "um"
    assert normalize_unit("um") == "um"
    assert normalize_unit("mm") == "mm"
    assert normalize_unit("CM") == "cm"


def test_unit_conversions():
    assert unit_to_um(1, "mm") == 1000.0
    assert unit_to_um(1, "cm") == 10000.0
    assert um_to_unit(1000, "mm") == 1.0
    assert convert_length(1, "mm", "um") == 1000.0
    assert convert_length(1000, "um", "mm") == pytest.approx(1.0)


def test_pixel_length():
    assert compute_pixel_length((0, 0), (3, 4)) == 5.0


def test_real_per_pixel():
    assert compute_real_per_pixel(1000, 224) == pytest.approx(1000 / 224)
    with pytest.raises(CalibrationError):
        compute_real_per_pixel(1000, 0)


def test_build_scale_um():
    # HJ98-like: ~224 px = 1000 um
    scale = build_scale_calibration((1200, 1080), (1424, 1080), 1000, "um")
    assert scale.pixel_length == pytest.approx(224.0)
    assert scale.unit == "um"
    assert scale.real_per_pixel == pytest.approx(1000 / 224)
    assert scale.confirmed is True
    assert real_per_pixel_um(scale) == pytest.approx(1000 / 224)


def test_build_scale_mm():
    scale = build_scale_calibration((0, 0), (225, 0), 1.0, "mm")
    assert scale.unit == "mm"
    assert scale.real_per_pixel == pytest.approx(1.0 / 225)
    # 225 px -> 1 mm = 1000 um
    assert length_px_to_real(225, scale, "um") == pytest.approx(1000.0)
    assert length_px_to_real(225, scale, "mm") == pytest.approx(1.0)


def test_length_and_area_without_scale():
    assert length_px_to_real(10, None) is None
    assert area_px_to_real(100, None) is None


def test_area_conversion():
    scale = build_scale_calibration((0, 0), (100, 0), 1000, "um")
    # 1 px = 10 um; 100 px^2 = 100 * 100 um^2 = 10000 um^2
    assert area_px_to_real(100, scale, "um") == pytest.approx(100 * 10 * 10)
    assert area_px_to_real(100, scale, "mm") == pytest.approx(100 * 0.01 * 0.01)


def test_identical_points_fail():
    with pytest.raises(CalibrationError):
        build_scale_calibration((1, 1), (1, 1), 1000, "um")
