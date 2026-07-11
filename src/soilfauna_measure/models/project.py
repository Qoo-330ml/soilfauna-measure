"""Project root model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from soilfauna_measure.models.category import Category, default_categories
from soilfauna_measure.models.image_record import ImageRecord

SCHEMA_VERSION = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Project:
    schema_version: str = SCHEMA_VERSION
    project_name: str = "untitled"
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    app_version: str = "0.1.0"
    categories: list[Category] = field(default_factory=default_categories)
    images: list[ImageRecord] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def find_image(self, image_id: str) -> ImageRecord | None:
        for img in self.images:
            if img.image_id == image_id:
                return img
        return None

    def find_image_by_path(self, relative_path: str) -> ImageRecord | None:
        rel = relative_path.replace("\\", "/")
        for img in self.images:
            if img.relative_path.replace("\\", "/") == rel:
                return img
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_name": self.project_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "app_version": self.app_version,
            "categories": [c.to_dict() for c in self.categories],
            "images": [i.to_dict() for i in self.images],
            "settings": dict(self.settings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        cats = [Category.from_dict(c) for c in (data.get("categories") or [])]
        if not cats:
            cats = default_categories()
        images = [ImageRecord.from_dict(i) for i in (data.get("images") or [])]
        return cls(
            schema_version=str(data.get("schema_version") or SCHEMA_VERSION),
            project_name=str(data.get("project_name") or "untitled"),
            created_at=str(data.get("created_at") or _utc_now_iso()),
            updated_at=str(data.get("updated_at") or _utc_now_iso()),
            app_version=str(data.get("app_version") or "0.1.0"),
            categories=cats,
            images=images,
            settings=dict(data.get("settings") or {}),
        )

    @classmethod
    def create_new(cls, project_name: str, app_version: str = "0.1.0") -> Project:
        now = _utc_now_iso()
        return cls(
            schema_version=SCHEMA_VERSION,
            project_name=project_name,
            created_at=now,
            updated_at=now,
            app_version=app_version,
            categories=default_categories(),
            images=[],
            settings={
                "default_scale_unit": "um",
                "show_scale_overlay": True,
            },
        )
