"""Reference libraries: one per kind, each a saved combination of reference media by path.

Why a library is per kind: a reference image and a reference audio are different material
for different ports, and a project that has character images says nothing about which
voice clips belong to it. When both kinds shared one file, the audio loader offered the
image loader's projects and the other way round, and a bin named for a story looked like
it contained both. So each kind has its own library root, its own project list, and its
own one-list file:

    <output>/h3-lvm-image-refs/<project>/h3lvm_references.json
    <output>/h3-lvm-audio-refs/<project>/h3lvm_references.json

Nothing here reads or writes media bytes. A preset stores exactly what a card already
stores - a {filename, subfolder, type} path, plus an audio window - so it costs a few
hundred bytes however big the media is. Each list goes through the same parser the node
uses, so a preset can never hold something the loader would reject nor be longer than the
slots it would have to fill.

The layout before this split kept both kinds in one file inside the video project bin
(<output>/h3-lvm/<project>/h3lvm_references.json). load_references() still reads that file
once and copies the kind's list into its own library, so a preset saved before the split
does not disappear.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from typing import Any, Dict, List

from ..core.ref_media import MAX_REF_AUDIOS, MAX_REF_IMAGES, parse_media_list
from .segment_store import (
    MAX_PROJECT_NAME_LENGTH,
    get_base_dir,
    get_project_dir,
    sanitize_project_name,
)

logger = logging.getLogger(__name__)

PRESET_NAME = "h3lvm_references.json"

# One library root per kind, and the slot limit that kind's loader has.
KIND_ROOTS = {"image": "h3-lvm-image-refs", "audio": "h3-lvm-audio-refs"}
KIND_LIMITS = {"image": MAX_REF_IMAGES, "audio": MAX_REF_AUDIOS}

# A per-kind library file holds one list; the shared pre-split file held one per kind.
LIST_KEY = "references"
LEGACY_KEYS = {"image": "images", "audio": "audios"}

_locks: Dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def check_kind(kind: Any) -> str:
    """The kind a caller asked for, or a Chinese error the panel can show."""
    if kind not in KIND_ROOTS:
        raise ValueError("参考库类型只能是 image 或 audio。")
    return str(kind)


def library_dir(kind: Any, create: bool = False) -> str:
    """The root of one kind's library (a sibling of the video bin root)."""
    check_kind(kind)
    path = os.path.join(get_base_dir(), KIND_ROOTS[str(kind)])
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def ref_project_dir(kind: Any, project: Any, create: bool = True) -> str:
    """One project inside one kind's library."""
    check_kind(kind)
    path = os.path.join(library_dir(kind), sanitize_project_name(project))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def preset_path(kind: Any, project: Any) -> str:
    """Where that project's preset lives."""
    return os.path.join(ref_project_dir(kind, project, create=False), PRESET_NAME)


def _library_lock(kind: str, name: str):
    key = os.path.normcase(os.path.realpath(ref_project_dir(kind, name, create=False)))
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _locks[key] = lock
        return lock


def _empty(name: str) -> Dict[str, Any]:
    return {"project_name": name, LIST_KEY: []}


def _read_list(kind: str, raw: Any) -> List[Dict[str, Any]]:
    """Re-parse a stored list: media folders may have moved since it was written."""
    try:
        return parse_media_list(raw, KIND_LIMITS[kind])
    except ValueError:
        return []


def _migrate_legacy(kind: str, name: str) -> Dict[str, Any]:
    """Copy one kind out of the pre-split shared file, once.

    That file is still the user's work, so the first read of a kind that has no library
    yet moves its list into its own library and reports it. An empty or unreadable legacy
    file stays empty - it must not create a bin the user never asked for.
    """
    legacy = os.path.join(get_project_dir(name, create=False), PRESET_NAME)
    if not os.path.isfile(legacy):
        return _empty(name)
    try:
        with open(legacy, "r", encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, ValueError):
        logger.warning("[H3 Ref Libraries] Unreadable legacy preset for '%s'", name)
        return _empty(name)
    data = raw if isinstance(raw, dict) else {}
    cleaned = _read_list(kind, data.get(LEGACY_KEYS[kind], []))
    if not cleaned:
        return _empty(name)
    _write_preset(kind, name, cleaned)
    logger.info("[H3 Ref Libraries] Copied the %s preset of '%s' out of the shared file (%d entries)",
                kind, name, len(cleaned))
    return {"project_name": name, LIST_KEY: cleaned}


def load_references(kind: Any, project: Any) -> Dict[str, Any]:
    """One project's preset in one kind's library; missing or unreadable reads as empty.

    The cards in the graph are the source of truth and a preset is a convenience, so a
    half-written file must not break the panel: it reads as empty and the next save
    rewrites it.
    """
    kind = check_kind(kind)
    name = sanitize_project_name(project)
    path = preset_path(kind, name)
    if not os.path.isfile(path):
        return _migrate_legacy(kind, name)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, ValueError):
        logger.warning("[H3 Ref Libraries] Unreadable %s preset for '%s': starting empty", kind, name)
        return _empty(name)

    data = raw if isinstance(raw, dict) else {}
    out = _empty(name)
    out[LIST_KEY] = _read_list(kind, data.get(LIST_KEY, []))
    return out


def _write_preset(kind: str, name: str, entries: List[Dict[str, Any]]) -> None:
    project_dir = ref_project_dir(kind, name)  # Creates the bin: a preset is a valid reason for it.
    handle, temp = tempfile.mkstemp(prefix=".refs_", dir=project_dir)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"project_name": name, LIST_KEY: entries}, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, os.path.join(project_dir, PRESET_NAME))
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def save_references(kind: Any, project: Any, entries: Any) -> Dict[str, Any]:
    """Replace one project's preset with the cards currently in the panel.

    Paths only, never the media. The list is validated by the node's own parser, so the
    stored preset is guaranteed loadable, and it can only ever be read by the loader of
    that kind - the other kind's library is a different folder and is never touched.
    """
    kind = check_kind(kind)
    name = sanitize_project_name(project)
    try:
        cleaned = parse_media_list(entries, KIND_LIMITS[kind])
    except ValueError as exc:
        raise ValueError("预设内容无法保存：%s" % exc) from None

    with _library_lock(kind, name):
        _write_preset(kind, name, cleaned)

    logger.info("[H3 Ref Libraries] Saved the %s preset for '%s' (%d entries)", kind, name, len(cleaned))
    return {"name": name, "kind": kind, "saved": len(cleaned)}


def count_references(kind: Any, project: Any) -> int:
    """How many cards one project's preset holds.

    The project menu prints this beside the bin name so a name is never chosen from
    memory. A missing or broken preset counts as zero, which is what load_references()
    returns for it; counting never creates a bin.
    """
    return len(load_references(kind, project)[LIST_KEY])


def list_reference_projects(kind: Any) -> List[Dict[str, Any]]:
    """Every project in one kind's library, with its card count.

    A library bin is a folder that holds a preset file - an empty project holds an empty
    list, which is still a valid place to save the next combination, so nothing here is
    filtered out.
    """
    kind = check_kind(kind)
    base = library_dir(kind)
    if not os.path.isdir(base):
        return []
    out: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(base)):
        if os.path.isfile(os.path.join(base, name, PRESET_NAME)):
            out.append({"name": name, LIST_KEY: count_references(kind, name)})
    return out


def _checked_name(project: Any) -> str:
    typed = str("" if project is None else project).strip()
    if not any(c.isalnum() for c in typed):
        raise ValueError("项目名称里至少要有一个字母或数字（例如「科幻短片 01」）。")
    name = sanitize_project_name(typed)
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError("项目名称太长，请控制在 %d 个字符以内。" % MAX_PROJECT_NAME_LENGTH)
    return name


def create_reference_project(kind: Any, project: Any) -> Dict[str, Any]:
    """Create an empty project in one kind's library, or confirm an existing one.

    Creating is idempotent - an existing name is selected, not duplicated - and the name
    returned is the sanitized one the folder really uses, so the menu can never drift
    from disk. An empty preset is written because list_reference_projects() only offers
    folders that already have one; without it a new project would stay invisible.
    """
    kind = check_kind(kind)
    name = _checked_name(project)
    with _library_lock(kind, name):
        existed = os.path.isfile(preset_path(kind, name))
        if not existed:
            _write_preset(kind, name, [])
    logger.info("[H3 Ref Libraries] %s the %s project '%s'",
                "Reusing" if existed else "Created", kind, name)
    return {"name": name, "kind": kind, "created": not existed, LIST_KEY: count_references(kind, name)}


def delete_reference_project(kind: Any, project: Any, confirm: Any = "") -> Dict[str, Any]:
    """Delete a whole project from one kind's library.

    The mirror of create_reference_project - same name rules, and ``confirm`` has to
    repeat the sanitized name so a panel left open on another project cannot empty the
    wrong folder. Only this kind's library is touched: deleting the audio project of a
    story must not remove its image references.
    """
    kind = check_kind(kind)
    name = _checked_name(project)
    if str("" if confirm is None else confirm).strip() != name:
        raise ValueError("请先确认要删除的项目名称，再按删除。")
    with _library_lock(kind, name):
        base = os.path.realpath(library_dir(kind))
        target = os.path.realpath(os.path.join(base, name))
        if target == base or os.path.dirname(target) != base:
            raise ValueError("项目名称无效，只能删除参考库内的项目文件夹。")
        if not os.path.isdir(target):
            return {"name": name, "kind": kind, "deleted": False, LIST_KEY: 0}
        cards = count_references(kind, name)
        shutil.rmtree(target)  # Never hide permission / in-use errors from the UI.
    logger.info("[H3 Ref Libraries] Deleted the %s project '%s' (%d cards)", kind, name, cards)
    return {"name": name, "kind": kind, "deleted": True, LIST_KEY: cards}
