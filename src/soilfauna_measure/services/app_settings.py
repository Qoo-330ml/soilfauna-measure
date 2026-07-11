"""Persistent application settings (recent workspaces, prefs)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings


ORG = "SoilFaunaMeasure"
APP = "SoilFaunaMeasure"


def _settings() -> QSettings:
    return QSettings(ORG, APP)


def get_recent_workspaces(max_items: int = 12) -> list[str]:
    s = _settings()
    raw = s.value("recent_workspaces", [])
    if not isinstance(raw, list):
        raw = []
    out: list[str] = []
    seen: set[str] = set()
    for p in raw:
        path = str(p)
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
        if len(out) >= max_items:
            break
    return out


def add_recent_workspace(path: Path | str, max_items: int = 12) -> list[str]:
    path = str(Path(path).expanduser().resolve())
    items = [path] + [p for p in get_recent_workspaces(max_items) if p != path]
    items = items[:max_items]
    s = _settings()
    s.setValue("recent_workspaces", items)
    s.sync()
    return items


def clear_recent_workspaces() -> None:
    s = _settings()
    s.setValue("recent_workspaces", [])
    s.sync()


def get_last_workspace() -> str | None:
    s = _settings()
    v = s.value("last_workspace", "")
    return str(v) if v else None


def set_last_workspace(path: Path | str | None) -> None:
    s = _settings()
    if path is None:
        s.remove("last_workspace")
    else:
        s.setValue("last_workspace", str(Path(path).expanduser().resolve()))
    s.sync()


def get_bool(key: str, default: bool = False) -> bool:
    s = _settings()
    v = s.value(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in {"1", "true", "yes"}
    return bool(v)


def set_bool(key: str, value: bool) -> None:
    s = _settings()
    s.setValue(key, value)
    s.sync()
