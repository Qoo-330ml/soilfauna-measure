"""Atomic project file read/write."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from soilfauna_measure.models.project import SCHEMA_VERSION, Project

logger = logging.getLogger(__name__)

PROJECT_FILENAME = "project.sfm.json"
PROJECT_BAK_SUFFIX = ".bak"
AUTOSAVE_FILENAME = "project.sfm.autosave.json"


class ProjectIOError(Exception):
    """Project load/save failure."""


def project_file_path(workspace_root: Path) -> Path:
    return Path(workspace_root) / PROJECT_FILENAME


def autosave_file_path(workspace_root: Path) -> Path:
    return Path(workspace_root) / "autosave" / AUTOSAVE_FILENAME


def load_project(path: Path | str) -> Project:
    """Load project JSON from path."""
    path = Path(path)
    if not path.is_file():
        raise ProjectIOError(f"Project file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectIOError(f"Corrupt project JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise ProjectIOError(f"Cannot read project: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProjectIOError("Project root must be a JSON object")

    version = str(data.get("schema_version") or "")
    if version and version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        # Future: migration. For now only same major.
        raise ProjectIOError(
            f"Unsupported schema_version {version!r}; this app uses {SCHEMA_VERSION}"
        )

    try:
        return Project.from_dict(data)
    except Exception as exc:  # noqa: BLE001
        raise ProjectIOError(f"Invalid project structure: {exc}") from exc


def save_project(
    project: Project,
    path: Path | str,
    *,
    make_backup: bool = True,
) -> None:
    """Atomically write project JSON.

    Writes to a temp file in the same directory, optionally backs up the
    existing file to ``.bak``, then ``os.replace`` into place.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    project.touch()
    payload = project.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        prefix=".project_",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

        if make_backup and path.is_file():
            bak = Path(str(path) + PROJECT_BAK_SUFFIX)
            try:
                shutil.copy2(path, bak)
            except OSError as exc:
                logger.warning("Could not write backup %s: %s", bak, exc)

        os.replace(tmp_path, path)
        logger.info("Saved project: %s", path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def save_autosave(project: Project, workspace_root: Path) -> Path:
    """Write autosave snapshot (still atomic, no .bak)."""
    path = autosave_file_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_project(project, path, make_backup=False)
    return path


def load_autosave(workspace_root: Path) -> Project | None:
    path = autosave_file_path(workspace_root)
    if not path.is_file():
        return None
    return load_project(path)


def dump_project_dict(project: Project) -> dict[str, Any]:
    """Expose serialised dict for tests."""
    return project.to_dict()
