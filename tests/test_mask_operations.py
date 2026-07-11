"""Mask geometry and area tests."""

import numpy as np
import pytest

from soilfauna_measure.core.mask_operations import (
    apply_brush_stroke,
    apply_disk_brush,
    empty_mask,
    mask_area_px,
    mask_to_contour,
    point_in_mask,
    polygon_to_mask,
)


def test_empty_area():
    m = empty_mask(10, 12)
    assert m.shape == (10, 12)
    assert mask_area_px(m) == 0


def test_polygon_square_area():
    # 10x10 square from (5,5) to (15,15) inclusive-ish fill
    pts = [[5, 5], [15, 5], [15, 15], [5, 15]]
    m = polygon_to_mask(pts, height=30, width=30)
    area = mask_area_px(m)
    # PIL polygon fill ~ 11*11 = 121
    assert 100 <= area <= 130
    assert point_in_mask(m, 10, 10)
    assert not point_in_mask(m, 0, 0)


def test_brush_add_and_erase():
    m = empty_mask(50, 50)
    apply_disk_brush(m, 25, 25, 5, value=255)
    a1 = mask_area_px(m)
    assert a1 > 50
    apply_brush_stroke(m, [[25, 25], [30, 25]], 3, value=0)
    a2 = mask_area_px(m)
    assert a2 < a1


def test_contour_nonempty():
    pts = [[10, 10], [40, 10], [40, 40], [10, 40]]
    m = polygon_to_mask(pts, 60, 60)
    contour = mask_to_contour(m)
    assert len(contour) >= 3


def test_two_objects_independent():
    m1 = polygon_to_mask([[0, 0], [10, 0], [10, 10], [0, 10]], 40, 40)
    m2 = polygon_to_mask([[20, 20], [30, 20], [30, 30], [20, 30]], 40, 40)
    assert mask_area_px(m1) > 0
    assert mask_area_px(m2) > 0
    # no overlap of nonzeros in same cells for these disjoint rects
    assert np.count_nonzero((m1 > 0) & (m2 > 0)) == 0
