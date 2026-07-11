"""Coordinate helper tests."""

from soilfauna_measure.core.coordinate_utils import clamp_to_image, pixel_distance


def test_clamp_inside():
    x, y = clamp_to_image(10.5, 20.25, 100, 80)
    assert x == 10.5
    assert y == 20.25


def test_clamp_outside():
    x, y = clamp_to_image(-5, 999, 100, 80)
    assert x == 0.0
    assert y < 80
    assert y > 79


def test_clamp_inclusive():
    x, y = clamp_to_image(100, 80, 100, 80, inclusive_max=True)
    assert x == 100.0
    assert y == 80.0


def test_clamp_zero_size():
    assert clamp_to_image(1, 1, 0, 0) == (0.0, 0.0)


def test_pixel_distance():
    assert pixel_distance(0, 0, 3, 4) == 5.0
    assert pixel_distance(1, 1, 1, 1) == 0.0
