"""Length path clipping / split after erase → independent objects."""

from pathlib import Path

import numpy as np

from soilfauna_measure.core.mask_operations import (
    apply_brush_stroke,
    connected_mask_parts,
    empty_mask,
    ensure_binary_mask,
    split_mask_by_polylines,
)
from soilfauna_measure.core.measurement import (
    longest_length_run,
    polyline_length_px,
    split_length_path_by_mask,
)
from soilfauna_measure.models.image_record import ImageRecord
from soilfauna_measure.models.specimen import SpecimenObject
from soilfauna_measure.services.object_service import ObjectService


def _bar_mask(h=40, w=80, y0=15, y1=25, x0=5, x1=75) -> np.ndarray:
    m = empty_mask(h, w)
    m[y0:y1, x0:x1] = 255
    return m


def test_split_length_when_middle_erased():
    mask = _bar_mask()
    # Vertical erase through the middle of the bar
    apply_brush_stroke(mask, [[40, 10], [40, 30]], radius=4, value=0)
    mask = ensure_binary_mask(mask)

    length = [[10, 20], [25, 20], [40, 20], [55, 20], [70, 20]]
    runs = split_length_path_by_mask(length, mask, margin=1)
    assert len(runs) >= 2
    # Left and right pieces both survive
    assert all(len(r) >= 2 for r in runs)
    left = runs[0]
    right = runs[-1]
    assert left[0][0] < 40
    assert right[-1][0] > 40


def test_longest_run_picks_longer():
    a = [[0, 0], [10, 0]]
    b = [[0, 0], [30, 0], [60, 0]]
    best = longest_length_run([a, b])
    assert polyline_length_px(best) == polyline_length_px(b)


def test_connected_parts_after_cut_4conn():
    mask = _bar_mask()
    apply_brush_stroke(mask, [[40, 10], [40, 30]], radius=5, value=0)
    parts = connected_mask_parts(mask, min_area=20, connectivity=1)
    assert len(parts) == 2


def test_split_mask_by_two_length_runs():
    # Connected bar + two length halves (as if path cut but mask bridges)
    mask = _bar_mask()
    left = [[10, 20], [25, 20], [35, 20]]
    right = [[45, 20], [55, 20], [70, 20]]
    parts = split_mask_by_polylines(mask, [left, right], min_area=20)
    assert len(parts) == 2


def test_intact_length_stays_one_run():
    mask = _bar_mask()
    length = [[10, 20], [40, 20], [70, 20]]
    runs = split_length_path_by_mask(length, mask, margin=1)
    assert len(runs) == 1
    assert len(runs[0]) == 3


def test_paint_erase_creates_two_objects(tmp_path: Path):
    """End-to-end: erase through a bar → two independent SpecimenObjects."""
    root = tmp_path
    (root / "masks").mkdir()
    svc = ObjectService()
    svc.set_workspace(root)
    rec = ImageRecord(
        image_id="img1",
        relative_path="images/a.png",
        width=80,
        height=40,
    )
    svc.bind_image(rec, width=80, height=40)

    mask = _bar_mask()
    obj = svc.create_from_mask(rec, mask, scale=None, category_id="unclassified")
    svc.apply_length_points(
        obj,
        [[10, 20], [25, 20], [40, 20], [55, 20], [70, 20]],
        scale=None,
        source="manual",
    )
    oid = obj.object_id
    assert len(rec.objects) == 1

    result = svc.paint_brush(
        rec,
        oid,
        [[40, 10], [40, 30]],
        radius=5,
        erase=True,
        scale=None,
        min_part_area=20,
    )
    assert isinstance(result, list)
    assert len(result) == 2
    assert len(rec.objects) == 2
    ids = {o.object_id for o in rec.objects}
    assert oid not in ids  # original replaced
    assert all(o.object_id in ids for o in result)
    # Each half should keep a length piece
    with_len = [o for o in result if o.length_points and len(o.length_points) >= 2]
    assert len(with_len) >= 1
