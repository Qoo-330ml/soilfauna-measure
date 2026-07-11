"""Commands for body-length path edits."""

from __future__ import annotations

from typing import Callable, Sequence

from soilfauna_measure.commands.base_command import Command
from soilfauna_measure.core.measurement import apply_length_to_object, copy_points
from soilfauna_measure.models.calibration import ScaleCalibration
from soilfauna_measure.models.specimen import SpecimenObject


class SetLengthPointsCommand(Command):
    """Replace an object's length_points (one undo unit)."""

    def __init__(
        self,
        obj: SpecimenObject,
        new_points: Sequence[Sequence[float]],
        scale: ScaleCalibration | None,
        *,
        on_applied: Callable[[SpecimenObject], None] | None = None,
        description: str = "edit length path",
    ) -> None:
        self._obj = obj
        self._before = copy_points(obj.length_points)
        self._after = copy_points(new_points)
        self._scale = scale
        self._on_applied = on_applied
        self.description = description
        # also preserve length_source before
        self._before_source = obj.length_source

    def execute(self) -> None:
        self._apply(self._after, source="manual" if self._after else "none")

    def undo(self) -> None:
        self._apply(self._before, source=self._before_source)

    def _apply(self, points: list[list[float]], *, source: str) -> None:
        fields = apply_length_to_object(points, self._scale)
        self._obj.length_points = fields["length_points"]
        self._obj.length_px = fields["length_px"]
        self._obj.length_um = fields["length_um"]
        self._obj.length_mm = fields["length_mm"]
        self._obj.length_source = source if points else "none"
        if fields["length_source"] == "none":
            self._obj.length_source = "none"
        if self._on_applied:
            self._on_applied(self._obj)
