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
stores - a {filename, subfolder, type} path, an optional display label, plus an audio
window - so it costs a few hundred bytes however big the media is. Each list goes through the same parser the node
uses, so a preset can never hold something the loader would reject nor be longer than the
slots it would have to fill.

The layout before this split kept both kinds in one file inside the video project bin
(<output>/h3-lvm/<project>/h3lvm_references.json). load_references() still reads that file
once and copies the kind's list into its own library, so a preset saved before the split
does not disappear.
"""
from __future__ import annotations

import filecmp
import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

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

# Where the reference loaders upload their media inside ComfyUI's input folder. One
# top-level folder makes every file this plugin imported identifiable at a glance;
# the kind subfolder keeps an image preset from ever pointing at an audio file.
INPUT_ROOT = "h3-lvm-refs"
INPUT_ROOTS = {"image": INPUT_ROOT + "/image", "audio": INPUT_ROOT + "/audio"}

# A per-kind library file holds one list; the shared pre-split file held one per kind.
LIST_KEY = "references"
LEGACY_KEYS = {"image": "images", "audio": "audios"}

_locks: Dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()
_rename_lock = threading.Lock()


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


_input_dir_override: Optional[str] = None


def set_input_dir_override(path: Optional[str]) -> None:
    """Tests only: redirect the input folder the reference media lives under."""
    global _input_dir_override
    _input_dir_override = path


def _input_dir() -> str:
    if _input_dir_override:
        return _input_dir_override
    try:
        import folder_paths
        path = folder_paths.get_input_directory()
    except Exception:
        path = None
    return path or os.path.join(".", "input")


def input_media_dir(kind: Any, create: bool = False) -> str:
    """The kind folder inside ComfyUI's input directory."""
    check_kind(kind)
    path = os.path.join(_input_dir(), INPUT_ROOT, str(kind))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def input_project_dir(kind: Any, project: Any, create: bool = False) -> str:
    """The per-project folder that actually holds this kind's uploads."""
    check_kind(kind)
    path = os.path.join(input_media_dir(kind), sanitize_project_name(project))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


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


def _entry_source(kind: str, entry: Dict[str, Any]) -> Optional[str]:
    """Where one card's file really is right now, before it is adopted.

    Only the two layouts this plugin used before are considered: the input root and
    the first migration's kind folder. A card that already sits in a deliberate folder
    is somebody's arrangement and is never second-guessed.
    """
    filename = str(entry.get("filename") or "")
    if not filename:
        return None
    if str(entry.get("subfolder") or "") == INPUT_ROOTS[kind]:
        candidates = [os.path.join(input_media_dir(kind), filename),
                      os.path.join(_input_dir(), filename)]
    else:
        candidates = [os.path.join(_input_dir(), filename),
                      os.path.join(input_media_dir(kind), filename)]
    checked = set()
    for path in candidates:
        real = os.path.realpath(path)
        if real in checked:
            continue
        checked.add(real)
        if os.path.isfile(real):
            return real
    return None


def _adopt_input_entries(kind: str, project: str, entries: List[Dict[str, Any]]) -> tuple:
    """Point one preset's input cards at copies inside its project folder.

    Copies, never moves: the files the preset used before stay where older workflows
    still look for them. An existing destination is only accepted when it holds the
    same bytes, so a newer upload under the same name is never overwritten. Returns
    (how many entries were repointed, the destination copies used).
    """
    changed = 0
    copies = []
    target_subfolder = INPUT_ROOTS[kind] + "/" + sanitize_project_name(project)
    for entry in entries:
        if entry.get("type") != "input":
            continue
        current = str(entry.get("subfolder") or "")
        if current == target_subfolder:
            continue
        if current not in ("", INPUT_ROOTS[kind]):
            continue
        source = _entry_source(kind, entry)
        if not source:
            continue
        filename = str(entry.get("filename") or "")
        target = os.path.join(input_project_dir(kind, project, create=True), filename)
        if os.path.exists(target):
            if not filecmp.cmp(source, target, shallow=False):
                logger.warning(
                    "[H3 Ref Libraries] %s already holds a different file named '%s'; "
                    "leaving the preset on its old location", os.path.dirname(target), filename)
                continue
        else:
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                logger.warning("[H3 Ref Libraries] Could not copy '%s' into %s: %s",
                               filename, os.path.dirname(target), exc)
                continue
        entry["subfolder"] = target_subfolder
        copies.append(target)
        changed += 1
    return changed, copies


def _clean_kind_root(kind: str, projects: List[tuple], copies: List[str]) -> int:
    """Drop first-migration copies once every preset has moved into project folders.

    Only a file that no preset references any more is removed, and only when a
    byte-identical copy exists in a project folder. Files uploaded but not yet saved
    into a preset are never adopted, so they are never removed either.
    """
    filenames = {os.path.basename(path) for path in copies}
    referenced = {
        str(entry.get("filename") or "")
        for _, entries in projects
        for entry in entries
        if str(entry.get("subfolder") or "") == INPUT_ROOTS[kind]
    }
    removed = 0
    for filename in sorted(filenames):
        if filename in referenced:
            continue
        source = os.path.join(input_media_dir(kind), filename)
        if not os.path.isfile(source):
            continue
        target = next((path for path in copies if os.path.basename(path) == filename), None)
        try:
            if target and filecmp.cmp(source, target, shallow=False):
                os.remove(source)
                removed += 1
        except OSError as exc:
            logger.warning("[H3 Ref Libraries] Could not remove the old copy %s: %s", source, exc)
    return removed


def migrate_input_media() -> Dict[str, int]:
    """One-time, idempotent regrouping of old presets into per-project folders.

    Uploads from the reference loaders live in ``<input>/h3-lvm-refs/<kind>/<project>``
    so one node's imports are easy to find and easy to clean per story. Presets from
    the input root and from the previous kind-only layout are copied into the project
    folder and rewritten; the old copies they leave behind are removed only after no
    preset references them any more. Missing files are left alone, so a stale card
    stays visibly stale instead of silently disappearing.
    """
    report = {"projects": 0, "entries": 0, "cleaned": 0}
    for kind in KIND_ROOTS:
        base = library_dir(kind)
        if not os.path.isdir(base):
            continue
        projects = []
        broken = False
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name, PRESET_NAME)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    raw = json.load(stream)
            except (OSError, ValueError):
                logger.warning("[H3 Ref Libraries] Unreadable %s preset for '%s': left unchanged", kind, name)
                broken = True
                continue
            data = raw if isinstance(raw, dict) else {}
            try:
                entries = parse_media_list(data.get(LIST_KEY, []), KIND_LIMITS[kind])
            except ValueError:
                logger.warning("[H3 Ref Libraries] Invalid %s preset for '%s': left unchanged", kind, name)
                broken = True
                continue
            projects.append((name, entries))

        copies = []
        for name, entries in projects:
            changed, made = _adopt_input_entries(kind, name, entries)
            copies.extend(made)
            if not changed:
                continue
            with _library_lock(kind, name):
                _write_preset(kind, name, entries)
            report["projects"] += 1
            report["entries"] += changed
            logger.info("[H3 Ref Libraries] Grouped the %s preset of '%s' into %s (%d entries)",
                        kind, name, INPUT_ROOTS[kind] + "/" + sanitize_project_name(name), changed)
        if not broken:
            report["cleaned"] += _clean_kind_root(kind, projects, copies)
    return report


def count_references(kind: Any, project: Any) -> int:
    """How many cards one project's preset holds.

    The project menu prints this beside the bin name so a name is never chosen from
    memory. A missing or broken preset counts as zero, which is what load_references()
    returns for it; counting never creates a bin.
    """
    return len(load_references(kind, project)[LIST_KEY])


def _reference_cover_url(kind: str, project: str, entries=None) -> str:
    """First reference card's /view URL; audio libraries have no image cover."""
    if kind != "image":
        return ""
    if entries is None:
        try:
            entries = load_references(kind, project)[LIST_KEY]
        except ValueError:
            return ""
    if not entries:
        return ""
    entry = entries[0]
    filename = str(entry.get("filename") or "")
    if not filename:
        return ""
    return "/view?" + urlencode({
        "filename": filename,
        "subfolder": str(entry.get("subfolder") or ""),
        "type": str(entry.get("type") or "input"),
    })


def _preset_updated_at(kind: str, project: str) -> str:
    try:
        mtime = os.path.getmtime(preset_path(kind, project))
    except OSError:
        return ""
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")


def list_reference_projects(kind: Any) -> List[Dict[str, Any]]:
    """Every project in one kind's library, with count, cover and update time.

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
        if not os.path.isfile(os.path.join(base, name, PRESET_NAME)):
            continue
        entries = load_references(kind, name)[LIST_KEY]
        out.append({
            "name": name,
            LIST_KEY: len(entries),
            "cover_url": _reference_cover_url(kind, name, entries),
            "updated_at": _preset_updated_at(kind, name),
        })
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


def rename_reference_project(kind: Any, project: Any, new_name: Any) -> Dict[str, Any]:
    """Rename one kind's reference project and rewrite its preset name."""
    kind = check_kind(kind)
    old = sanitize_project_name(project)
    new = _checked_name(new_name)
    if old == new:
        return {"old": old, "name": new, "kind": kind, "renamed": False}
    with _rename_lock, _library_lock(kind, old), _library_lock(kind, new):
        old_dir = ref_project_dir(kind, old, create=False)
        new_dir = ref_project_dir(kind, new, create=False)
        if not os.path.isfile(os.path.join(old_dir, PRESET_NAME)):
            raise FileNotFoundError("%s 参考库项目「%s」不存在。" % (kind, old))
        if os.path.exists(new_dir):
            raise ValueError("%s 参考库项目「%s」已存在，请换一个名字。" % (kind, new))
        shutil.move(old_dir, new_dir)
        try:
            entries = load_references(kind, new)[LIST_KEY]
            _write_preset(kind, new, entries)
        except Exception:
            shutil.move(new_dir, old_dir)
            raise
    logger.info("[H3 Ref Libraries] Renamed the %s project '%s' -> '%s'", kind, old, new)
    return {"old": old, "name": new, "kind": kind, "renamed": True}
