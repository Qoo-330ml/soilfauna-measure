"""Category model and default seeds."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Category:
    category_id: str
    name_zh: str
    name_en: str = ""
    color: str = "#007aff"
    shortcut: str | None = None
    measurement_note: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Category:
        return cls(
            category_id=str(data["category_id"]),
            name_zh=str(data.get("name_zh", data["category_id"])),
            name_en=str(data.get("name_en", "")),
            color=str(data.get("color", "#007aff")),
            shortcut=data.get("shortcut"),
            measurement_note=str(data.get("measurement_note", "")),
            enabled=bool(data.get("enabled", True)),
        )


def default_categories() -> list[Category]:
    """Seed categories — soft system-like palette."""
    return [
        Category("unclassified", "未分类", "Unclassified", "#8e8e93", "0"),
        Category("insect", "昆虫", "Insect", "#ff3b30", "1"),
        Category("mite", "螨类", "Mite", "#ff9f0a", "2"),
        Category("nematode", "线虫", "Nematode", "#34c759", "3"),
        Category("crustacean", "甲壳类", "Crustacean", "#007aff", "4"),
        Category("myriapod", "多足类", "Myriapod", "#af52de", "5"),
        Category("larva", "幼虫", "Larva", "#ffcc00", "6"),
        Category("other", "其他", "Other", "#5ac8fa", "7"),
    ]
