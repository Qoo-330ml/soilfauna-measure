"""Per-image project record."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from soilfauna_measure.models.calibration import ScaleCalibration
from soilfauna_measure.models.specimen import SpecimenObject


@dataclass
class ImageRecord:
    image_id: str
    relative_path: str
    width: int = 0
    height: int = 0
    channels: int = 0
    dtype: str = ""
    status: str = "pending"  # pending | in_progress | needs_review | done
    scale: ScaleCalibration | None = None
    objects: list[SpecimenObject] = field(default_factory=list)
    notes: str = ""
    thumbnail_path: str | None = None
    next_object_seq: int = 1  # for non-reusing object ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "relative_path": self.relative_path,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "dtype": self.dtype,
            "status": self.status,
            "scale": self.scale.to_dict() if self.scale else None,
            "objects": [o.to_dict() for o in self.objects],
            "notes": self.notes,
            "thumbnail_path": self.thumbnail_path,
            "next_object_seq": self.next_object_seq,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImageRecord:
        objs = [SpecimenObject.from_dict(o) for o in (data.get("objects") or [])]
        return cls(
            image_id=str(data["image_id"]),
            relative_path=str(data["relative_path"]),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            channels=int(data.get("channels") or 0),
            dtype=str(data.get("dtype") or ""),
            status=str(data.get("status") or "pending"),
            scale=ScaleCalibration.from_dict(data.get("scale")),
            objects=objs,
            notes=str(data.get("notes") or ""),
            thumbnail_path=data.get("thumbnail_path"),
            next_object_seq=int(data.get("next_object_seq") or 1),
        )
