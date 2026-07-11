"""Workspace directory layout, image import, and project binding."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from soilfauna_measure import __version__
from soilfauna_measure.core.image_loader import (
    SUPPORTED_EXTENSIONS,
    scan_image_files,
)
from soilfauna_measure.models.image_record import ImageRecord
from soilfauna_measure.models.project import Project
from soilfauna_measure.storage.project_io import (
    PROJECT_FILENAME,
    ProjectIOError,
    autosave_file_path,
    load_autosave,
    load_project,
    project_file_path,
    save_project,
)

logger = logging.getLogger(__name__)

WORKSPACE_SUBDIRS = (
    "images",
    "annotations",
    "masks",
    "crops",
    "thumbnails",
    "exports",
    "autosave",
)


@dataclass
class Workspace:
    """In-memory workspace: root folder + project document."""

    root: Path
    project: Project
    current_index: int = -1
    dirty: bool = False
    loaded_from_autosave: bool = False

    @property
    def images(self) -> list[ImageRecord]:
        return self.project.images

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    @property
    def project_path(self) -> Path:
        return project_file_path(self.root)

    @property
    def current(self) -> ImageRecord | None:
        if 0 <= self.current_index < len(self.images):
            return self.images[self.current_index]
        return None

    def abs_path(self, record: ImageRecord) -> Path:
        return (self.root / record.relative_path).resolve()

    def mark_dirty(self) -> None:
        self.dirty = True
        self.project.touch()


def ensure_workspace_dirs(root: Path) -> None:
    """Create standard workspace subdirectories if missing."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in WORKSPACE_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)


def _unique_dest(dest_dir: Path, name: str) -> Path:
    """Return a non-colliding destination path under dest_dir."""
    candidate = dest_dir / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _collect_source_images(folder: Path) -> list[Path]:
    """Collect images from folder root and optional images/ subfolder."""
    folder = Path(folder)
    found: dict[str, Path] = {}

    for p in scan_image_files(folder):
        found[p.name.lower()] = p

    images_sub = folder / "images"
    if images_sub.is_dir():
        for p in scan_image_files(images_sub):
            found[p.name.lower()] = p

    return sorted(found.values(), key=lambda p: p.name.lower())


def _import_images_to_workspace(root: Path) -> list[Path]:
    """Copy/discover images into images/; return sorted absolute paths."""
    images_dir = root / "images"
    sources = _collect_source_images(root)
    dests: list[Path] = []

    for src in sources:
        src = src.resolve()
        try:
            src.relative_to(images_dir.resolve())
            inside_images = True
        except ValueError:
            inside_images = False

        if inside_images:
            dest = src
        else:
            dest = images_dir / src.name
            if dest.resolve() != src:
                if not dest.exists():
                    logger.info("Copying %s -> %s", src, dest)
                    shutil.copy2(src, dest)
                elif dest.stat().st_size != src.stat().st_size:
                    dest = _unique_dest(images_dir, src.name)
                    logger.info("Name conflict; copying %s -> %s", src, dest)
                    shutil.copy2(src, dest)
        dests.append(dest.resolve())

    # unique by path
    uniq: dict[str, Path] = {str(p): p for p in dests}
    return sorted(uniq.values(), key=lambda p: p.name.lower())


def _sync_project_images(project: Project, image_paths: list[Path], root: Path) -> bool:
    """Merge filesystem images into project. Returns True if project changed."""
    changed = False
    by_rel = {
        img.relative_path.replace("\\", "/"): img for img in project.images
    }
    by_id = {img.image_id: img for img in project.images}
    new_list: list[ImageRecord] = []
    seen_rels: set[str] = set()

    for path in image_paths:
        rel = f"images/{path.name}"
        rel_key = rel.replace("\\", "/")
        seen_rels.add(rel_key)
        existing = by_rel.get(rel_key) or by_id.get(path.stem)
        if existing is not None:
            # Keep annotations; fix path if needed
            if existing.relative_path.replace("\\", "/") != rel_key:
                existing.relative_path = rel
                changed = True
            if existing.image_id != path.stem and existing.image_id not in by_id:
                pass
            new_list.append(existing)
        else:
            new_list.append(
                ImageRecord(
                    image_id=path.stem,
                    relative_path=rel,
                    status="pending",
                )
            )
            changed = True

    # Keep orphan records that no longer have files? Drop them for M2 simplicity
    # but preserve if user might re-add — drop with log
    for img in project.images:
        key = img.relative_path.replace("\\", "/")
        if key not in seen_rels and img not in new_list:
            logger.info("Image missing on disk, keeping record: %s", img.relative_path)
            new_list.append(img)

    # Sort by filename
    new_list.sort(key=lambda r: Path(r.relative_path).name.lower())
    if [i.image_id for i in project.images] != [i.image_id for i in new_list]:
        changed = True
    project.images = new_list
    return changed


def open_workspace(
    folder: Path | str,
    *,
    prefer_autosave: bool | None = None,
) -> Workspace:
    """Open or initialize a workspace folder and bind project.sfm.json.

    Policy:
    - Ensure standard subdirs.
    - Copy external images into ``images/``.
    - Load existing project or create new; merge image list.
    - If autosave is newer than main project, set ``loaded_from_autosave``
      when ``prefer_autosave`` is True; if None, load main and flag if autosave newer.
    """
    root = Path(folder).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Folder not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    ensure_workspace_dirs(root)
    image_paths = _import_images_to_workspace(root)

    proj_path = project_file_path(root)
    auto_path = autosave_file_path(root)
    loaded_from_autosave = False
    project: Project | None = None

    main_mtime = proj_path.stat().st_mtime if proj_path.is_file() else 0.0
    auto_mtime = auto_path.stat().st_mtime if auto_path.is_file() else 0.0
    autosave_newer = auto_mtime > main_mtime + 0.5

    if prefer_autosave is True and auto_path.is_file():
        try:
            project = load_autosave(root)
            loaded_from_autosave = True
            logger.info("Loaded project from autosave")
        except ProjectIOError:
            logger.exception("Autosave load failed; falling back")

    if project is None and proj_path.is_file():
        project = load_project(proj_path)
    if project is None and auto_path.is_file():
        try:
            project = load_autosave(root)
            loaded_from_autosave = True
        except ProjectIOError:
            pass

    if project is None:
        project = Project.create_new(
            project_name=root.name,
            app_version=__version__,
        )

    changed = _sync_project_images(project, image_paths, root)
    # Always persist brand-new project so reopen works
    need_initial_save = not proj_path.is_file()

    ws = Workspace(
        root=root,
        project=project,
        current_index=0 if project.images else -1,
        dirty=changed or need_initial_save,
        loaded_from_autosave=loaded_from_autosave or (
            prefer_autosave is None and autosave_newer and auto_path.is_file()
        ),
    )

    if need_initial_save:
        try:
            save_project(project, proj_path, make_backup=False)
            ws.dirty = changed  # only dirty if sync changed after initial
            if not changed:
                ws.dirty = False
        except OSError:
            logger.exception("Initial project save failed")

    logger.info(
        "Opened workspace %s with %d image(s), dirty=%s",
        root,
        len(project.images),
        ws.dirty,
    )
    return ws


def save_workspace(workspace: Workspace) -> None:
    """Write project.sfm.json for the workspace."""
    save_project(workspace.project, workspace.project_path, make_backup=True)
    workspace.dirty = False


def list_supported_extensions() -> list[str]:
    """Sorted list of supported extensions including the leading dot."""
    return sorted(SUPPORTED_EXTENSIONS)
