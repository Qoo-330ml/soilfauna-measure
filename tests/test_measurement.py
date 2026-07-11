"""Polyline body-length measurement tests."""

import pytest

from soilfauna_measure.commands.base_command import CommandStack
from soilfauna_measure.commands.length_commands import SetLengthPointsCommand
from soilfauna_measure.core.calibration import build_scale_calibration
from soilfauna_measure.core.measurement import (
    apply_length_to_object,
    nearest_point_index,
    nearest_segment_insert,
    polyline_length_px,
    reverse_points,
)
from soilfauna_measure.models.specimen import SpecimenObject


def test_polyline_length_right_triangle():
    pts = [[0, 0], [3, 0], [3, 4]]
    assert polyline_length_px(pts) == pytest.approx(7.0)


def test_polyline_single_point():
    assert polyline_length_px([[1, 1]]) == 0.0
    assert polyline_length_px([]) == 0.0


def test_apply_length_with_scale():
    scale = build_scale_calibration((0, 0), (100, 0), 1000, "um")
    # 100 px * 10 um/px = 1000 um
    fields = apply_length_to_object([[0, 0], [100, 0]], scale)
    assert fields["length_px"] == pytest.approx(100.0)
    assert fields["length_um"] == pytest.approx(1000.0)
    assert fields["length_mm"] == pytest.approx(1.0)
    assert fields["length_source"] == "manual"


def test_apply_length_without_scale():
    fields = apply_length_to_object([[0, 0], [10, 0]], None)
    assert fields["length_px"] == pytest.approx(10.0)
    assert fields["length_um"] is None
    assert fields["length_mm"] is None


def test_reverse_and_nearest():
    pts = [[0, 0], [10, 0], [20, 5]]
    rev = reverse_points(pts)
    assert rev[0] == [20, 5]
    assert nearest_point_index(pts, 10.1, 0.2, max_dist=2) == 1
    assert nearest_point_index(pts, 100, 100, max_dist=2) is None
    ins = nearest_segment_insert(pts, 5, 0.5, max_dist=2)
    assert ins is not None
    assert ins[0] == 1  # insert between 0 and 1


def test_length_command_undo_redo():
    obj = SpecimenObject(object_id="t_001")
    scale = build_scale_calibration((0, 0), (10, 0), 100, "um")
    stack = CommandStack()
    applied = []

    def on_applied(o):
        applied.append(list(o.length_points))

    stack.push(
        SetLengthPointsCommand(
            obj, [[0, 0], [10, 0]], scale, on_applied=on_applied
        )
    )
    assert obj.length_px == pytest.approx(10.0)
    assert obj.length_um == pytest.approx(100.0)

    stack.push(
        SetLengthPointsCommand(
            obj, [[0, 0], [10, 0], [10, 10]], scale, on_applied=on_applied
        )
    )
    assert obj.length_px == pytest.approx(20.0)

    assert stack.undo()
    assert obj.length_px == pytest.approx(10.0)
    assert len(obj.length_points) == 2

    assert stack.redo()
    assert obj.length_px == pytest.approx(20.0)
    assert len(obj.length_points) == 3
