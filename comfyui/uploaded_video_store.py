"""Uploaded videos: the Picker's second library, with its own root and its own index.

The cut-segment bin (segment_store) holds tensors the Manager or Smart Split produced.
This library holds the user's own video files, kept exactly as they were uploaded - no
cutting, no re-encoding, no safetensors. Both are reachable from one Picker node, so they
must never share a folder: a project named "sci-fi 01" in the upload library is not the
project named "sci-fi 01" that holds saved segments.

Layout (under the ComfyUI output directory, a SIBLING of the cut bin):

    h3-lvm-video-uploads/
      <project>/
        h3lvm_upload_index.json   # schema_version / next_id / videos[]
        files/
          vid001.mp4              # the uploaded bytes, renamed to an opaque id
          vid001_cover.jpg        # first-frame card cover

Why an opaque storage name: two uploads called shot.mp4 stay two cards, and a user
filename can never carry a path traversal into the filesystem. original_name keeps what
the card shows.

Two counters, on purpose. segment_id is the card's position: a project's cards always
number 1..N, so an import appends at the end and a delete moves the cards after it up one.
That is the rule a user reads off the panel, and it is why a gap never appears. next_id is
only the storage counter: it hands out the next vidNNN file name and never reuses one,
because the number a delete freed may now belong to a different card that moved into it.

Why reordering renumbers: the card number is how a workflow picks a card, so the order
arranged in the panel has to be the order the ids count in. The files keep the opaque
names they were given at import and every read goes through the record, so a reorder
writes one index and moves no bytes.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from .asset_paths import checked_asset_dir, preview_url
from .segment_store import DEFAULT_PROJECT, MAX_PROJECT_NAME_LENGTH, sanitize_project_name

logger = logging.getLogger(__name__)

BIN_DIR_NAME = "h3-lvm-video-uploads"
INDEX_NAME = "h3lvm_upload_index.json"
FILES_DIR_NAME = "files"
COVER_SUFFIX = "_cover.jpg"
PARTIAL_PREFIX = ".upload_"
SCHEMA_VERSION = 1

# The Picker's segment_id widget is an INT with max 999, so a card above that could never
# be selected. The cap is on how many cards one project holds - the storage names keep
# counting up on their own. Refusing beats handing out a number the node cannot reach.
MAX_SEGMENT_ID = 999

# The containers we are willing to hand to FFmpeg, and the subset a browser can play from
# /view. Both are reported to the panel; neither is trusted as proof the file is a video.
ALLOWED_SUFFIXES = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".ts", ".mts"}
BROWSER_PLAYABLE = {".mp4", ".m4v", ".webm", ".mov"}

# One upload is a clip, not a feature film. The cap is a boundary the API can report
# before the disk fills, not a claim that longer files are wrong.
MAX_UPLOAD_BYTES = 2 * 1024 ** 3

_base_dir_override: Optional[str] = None
_project_locks: Dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

def set_base_dir_override(path: Optional[str]) -> None:
    """Tests only: redirect the upload library root (e.g. a temp folder)."""
    global _base_dir_override
    _base_dir_override = path


def get_base_dir() -> str:
    """The upload library root - never inside the cut bin."""
    if _base_dir_override:
        return _base_dir_override
    try:
        import folder_paths
        out = folder_paths.get_output_directory()
    except Exception:
        out = os.path.join(".", "output")
    return os.path.join(out, BIN_DIR_NAME)


def get_project_dir(project: Any, create: bool = True) -> str:
    base = get_base_dir()
    pdir = os.path.join(base, sanitize_project_name(project))
    if create:
        os.makedirs(pdir, exist_ok=True)
    return pdir


def get_files_dir(project: Any, create: bool = True) -> str:
    """Where the original bytes and the covers of one project live."""
    path = checked_asset_dir(get_base_dir(), get_project_dir(project, create=create), FILES_DIR_NAME)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _project_lock(name: str):
    key = os.path.normcase(os.path.realpath(get_project_dir(name, create=False)))
    with _locks_guard:
        lock = _project_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _project_locks[key] = lock
        return lock


def project_locked(fn):
    signature = inspect.signature(fn)

    @wraps(fn)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        with _project_lock(sanitize_project_name(bound.arguments["project"])):
            return fn(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def _empty_index(name: str) -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "project_name": name, "next_id": 1, "videos": []}


def _order_key(record: Dict[str, Any]) -> Tuple[int, int]:
    """Sort cards by their number; a record without a readable one goes last."""
    value = record.get("segment_id")
    if isinstance(value, bool) or not isinstance(value, int):
        return (1, 0)
    return (0, value)


def _renumber(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Hand out fresh card numbers in the order given: the first card becomes 1.

    Import, delete and drag all end here, so the numbering has exactly one rule - the
    card's place in the deck - and a gap left by a delete closes by itself. The caller
    decides the order (by the old numbers, or by a drag), because re-sorting here would
    undo the drag. Records keep the storage_name they were given at import, so this
    writes one index and moves no bytes.
    """
    for position, record in enumerate(videos, start=1):
        record["segment_id"] = position
    return videos


def _write_index(project: str, idx: Dict[str, Any]) -> None:
    pdir = get_project_dir(project)
    fd, temp = tempfile.mkstemp(prefix=".index_", dir=pdir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(idx, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, os.path.join(pdir, INDEX_NAME))
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def index_path(project: Any) -> str:
    return os.path.join(get_project_dir(project, create=False), INDEX_NAME)


def load_upload_index(project: Any) -> Dict[str, Any]:
    """Read one project's index, or explain why it cannot be read.

    A missing index is an empty library - that is what a new project is. A damaged one is
    not: the video files are still on disk, so answering "empty" would invite the user to
    delete a folder they can still partly use.
    """
    name = sanitize_project_name(project)
    path = index_path(name)
    if not os.path.isfile(path):
        return _empty_index(name)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ValueError(
            "投放视频库的索引文件读不出来（%s），已保存的视频文件没有被删除。"
            "请检查 %s 是否被其他程序占用或已损坏。" % (exc.__class__.__name__, INDEX_NAME)
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("videos", []), list):
        raise ValueError("投放视频库的索引文件格式不正确，请检查 %s。" % INDEX_NAME)
    data.setdefault("project_name", name)
    data.setdefault("next_id", 1)
    data.setdefault("schema_version", SCHEMA_VERSION)
    return data


def _count_lenient(project: str) -> int:
    """Cards in one project, for a menu that lists every project.

    One unreadable index must not hide the other projects, so it counts as zero here;
    opening that project still reports the real error through load_upload_index().
    """
    try:
        return len(load_upload_index(project).get("videos", []))
    except ValueError:
        return 0


def list_upload_projects() -> List[Dict[str, Any]]:
    """Every project in the upload library, with its video count.

    Listing never creates a folder: a project is a directory that already holds an index.
    """
    base = get_base_dir()
    if not os.path.isdir(base):
        return []
    out: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(base)):
        if os.path.isfile(os.path.join(base, name, INDEX_NAME)):
            out.append({"name": name, "videos": _count_lenient(name)})
    return out


def count_uploads(project: Any) -> int:
    return len(load_upload_index(project).get("videos", []))


def _file_url(project: str, filename: str) -> str:
    return preview_url(os.path.join(get_files_dir(project, create=False), filename),
                       "%s/%s/%s" % (BIN_DIR_NAME, project, FILES_DIR_NAME))


@project_locked
def list_uploads(project: Any) -> Dict[str, Any]:
    """The index plus safe /view URLs, for the card panel."""
    name = sanitize_project_name(project)
    idx = load_upload_index(name)
    # The panel shows the cards in the order the library is numbered, and dragging a
    # card is how that order changes - so the sort is the invariant the drag leans on,
    # and a hand-edited index still reads top left to bottom right.
    idx["videos"] = sorted(idx.get("videos", []), key=_order_key)
    files_dir = get_files_dir(name, create=False)
    for video in idx.get("videos", []):
        cover = video.get("thumbnail", "")
        storage = video.get("storage_name", "")
        path = os.path.join(files_dir, storage) if storage else ""
        video["cover_url"] = (_file_url(name, cover)
                              if cover and os.path.isfile(os.path.join(files_dir, cover)) else "")
        video["video_url"] = _file_url(name, storage) if path and os.path.isfile(path) else ""
        video["missing_file"] = not (path and os.path.isfile(path))
        video["browser_preview"] = (os.path.splitext(storage)[1].lower() in BROWSER_PLAYABLE
                                    and not video["missing_file"])
    return idx


# ---------------------------------------------------------------------------
# Names and lookups
# ---------------------------------------------------------------------------

def _checked_name(project: Any) -> str:
    typed = str("" if project is None else project).strip()
    if not any(c.isalnum() for c in typed):
        raise ValueError("项目名称里至少要有一个字母或数字（例如「科幻短片 01」）。")
    name = sanitize_project_name(typed)
    if len(name) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError("项目名称太长，请控制在 %d 个字符以内。" % MAX_PROJECT_NAME_LENGTH)
    return name


def safe_suffix(original_name: Any) -> str:
    """The container suffix we are willing to store, taken from the user's filename.

    The extension is not proof of anything - probe_video still has to find a video stream -
    but it decides the file name on disk and the browser's MIME guess on /view, so an
    unknown one is refused rather than guessed at.
    """
    suffix = os.path.splitext(str("" if original_name is None else original_name))[1].lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("暂不支持这种视频格式：%s。可用格式：%s。"
                         % (suffix or "(没有扩展名)", "、".join(sorted(ALLOWED_SUFFIXES))))
    return suffix


def _storage_stem(segment_id: int) -> str:
    return "vid%03d" % int(segment_id)


def checked_upload_file(project: str, storage_name: Any) -> str:
    """Absolute path of one stored file, verified to stay inside that project.

    Storage names are generated here, so this is a guard against a hand-edited index and
    against a junction placed inside the files folder - not against user input.
    """
    files_dir = get_files_dir(project, create=False)
    root = os.path.normcase(os.path.realpath(files_dir))
    text = str(storage_name or "")
    target = os.path.abspath(os.path.join(files_dir, text))
    if (not text or os.path.basename(text) != text
            or os.path.normcase(os.path.realpath(target)) != os.path.normcase(os.path.join(root, text))):
        raise ValueError("视频文件路径不安全，已拒绝读取。")
    return target


def find_upload(project: Any, segment_id: Any) -> Optional[Dict[str, Any]]:
    """The index record for one card number, or None."""
    if isinstance(segment_id, bool) or not isinstance(segment_id, int) or segment_id < 1:
        raise ValueError("segment_id 必须是正整数。")
    name = sanitize_project_name(project)
    return next((v for v in load_upload_index(name).get("videos", [])
                 if v.get("segment_id") == segment_id), None)


@project_locked
def resolve_upload(project: Any, segment_id: Any) -> Tuple[str, Dict[str, Any]]:
    """Absolute path + record of one uploaded video, for the node to decode.

    The file may have been deleted outside ComfyUI since it was indexed; that is reported
    as a readable error naming the project and the id, not as a decode failure.
    """
    name = sanitize_project_name(project)
    record = find_upload(name, segment_id)
    if record is None:
        available = [v.get("segment_id") for v in load_upload_index(name).get("videos", [])]
        raise ValueError(
            "投放视频库「%s」里没有编号 %s 的视频。可用编号：%s。"
            "（编号就是卡片顺序：删掉一张卡片后，后面的卡片会顺延补位。）"
            % (name, segment_id, available if available else "(空)")
        )
    path = checked_upload_file(name, record.get("storage_name", ""))
    if not os.path.isfile(path):
        raise ValueError(
            "投放视频库「%s」编号 %s 的视频文件已不在磁盘上（%s）。请重新上传，或删除这张卡片。"
            % (name, segment_id, record.get("storage_name", ""))
        )
    return path, record


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------

def create_upload_project(project: Any) -> Dict[str, Any]:
    """Create an empty project in the upload library, or select the existing name.

    The empty index is written because list_upload_projects() only offers folders that
    already hold one - without it a new project would stay invisible.
    """
    name = _checked_name(project)
    with _project_lock(name):
        existed = os.path.isfile(index_path(name))
        if not existed:
            _write_index(name, _empty_index(name))
        get_files_dir(name, create=True)
        videos = _count_lenient(name)
    logger.info("[H3 LVM Uploads] %s project '%s'", "Reusing" if existed else "Created", name)
    return {"name": name, "created": not existed, "videos": videos}


def delete_upload_project(project: Any, confirm: Any = "") -> Dict[str, Any]:
    """Delete one upload project - and only that folder.

    The cut bin keeps its own folder of the same name; that is the whole point of two
    roots, so this function never looks at segment_store at all.
    """
    name = _checked_name(project)
    if str("" if confirm is None else confirm).strip() != name:
        raise ValueError("请先确认要删除的项目名称，再按删除。")
    with _project_lock(name):
        base = os.path.realpath(get_base_dir())
        target = os.path.realpath(os.path.join(base, name))
        if target == base or os.path.dirname(target) != base:
            raise ValueError("项目名称无效，只能删除投放视频库内的项目文件夹。")
        if not os.path.isdir(target):
            return {"name": name, "deleted": False, "videos": 0}
        videos = _count_lenient(name)
        shutil.rmtree(target)  # Never hide permission / in-use errors from the UI.
    logger.info("[H3 LVM Uploads] Deleted project '%s' (%d videos)", name, videos)
    return {"name": name, "deleted": True, "videos": videos}


# ---------------------------------------------------------------------------
# Import / delete one video
# ---------------------------------------------------------------------------

def open_partial(project: Any) -> Tuple[str, str]:
    """Where a streaming upload is written before it is verified.

    The name is checked here too, not only in create_upload_project: an upload that names
    a project the panel could never create is refused before a single byte is written,
    otherwise it would quietly land in the "default" folder.
    """
    files_dir = get_files_dir(_checked_name(project))
    fd, temp = tempfile.mkstemp(prefix=PARTIAL_PREFIX, suffix=".partial", dir=files_dir)
    os.close(fd)
    return files_dir, temp


@project_locked
def import_upload(project: Any, partial_path: str, original_name: Any) -> Dict[str, Any]:
    """Verify a streamed upload, move it into the library, and register one card.

    Order matters: probe first (a file with no video stream never enters the library),
    then the rename, then the cover, and the index last. Anything that fails afterwards
    removes its own files, so the panel can never show a card whose bytes are incomplete.
    """
    from .video_decode import TARGET_FPS, probe_video, write_cover

    name = _checked_name(project)
    suffix = safe_suffix(original_name)
    try:
        info = probe_video(partial_path)
    except Exception:
        _remove_quietly(partial_path)
        raise

    with _project_lock(name):
        idx = load_upload_index(name)
        videos = idx.get("videos", [])
        # The card number is the next position in the deck; next_id only names the file.
        storage_id = int(idx.get("next_id") or 1)
        if len(videos) + 1 > MAX_SEGMENT_ID:
            _remove_quietly(partial_path)
            raise ValueError(
                "投放视频库「%s」的卡片已到 %d 上限，无法再新增视频。请新建一个项目，或删除不再需要的卡片。"
                % (name, MAX_SEGMENT_ID)
            )
        stem = _storage_stem(storage_id)
        storage = stem + suffix
        cover = stem + COVER_SUFFIX
        files_dir = get_files_dir(name)
        final = checked_upload_file(name, storage)
        os.replace(partial_path, final)
        try:
            write_cover(final, os.path.join(files_dir, cover))
            record = {
                "segment_id": len(videos) + 1,
                "storage_name": storage,
                "original_name": os.path.basename(str(original_name or storage))[:160],
                "thumbnail": cover,
                "width": int(info["width"]),
                "height": int(info["height"]),
                "source_fps": info["source_fps"],
                "source_fps_num": info["source_fps_num"],
                "source_fps_den": info["source_fps_den"],
                "variable_fps": bool(info["variable_fps"]),
                "duration_sec": info["duration_sec"],
                "has_audio": bool(info["has_audio"]),
                "audio_streams": int(info.get("audio_streams") or 0),
                "out_fps": TARGET_FPS,
                "size_bytes": os.path.getsize(final),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            # Renumbering the whole deck keeps "the numbers are 1..N in card order" true
            # even for a hand-edited index, and leaves the new card last.
            idx["videos"] = _renumber(sorted(videos + [record], key=_order_key))
            idx["next_id"] = storage_id + 1
            idx["schema_version"] = SCHEMA_VERSION
            idx["project_name"] = name
            idx["updated_at"] = datetime.now().isoformat(timespec="seconds")
            _write_index(name, idx)
        except Exception:
            _remove_quietly(final)
            _remove_quietly(os.path.join(files_dir, cover))
            raise

    logger.info("[H3 LVM Uploads] Imported '%s' #%s into '%s' (%dx%d, %s fps, %s bytes)",
                record["original_name"], record["segment_id"], name, record["width"], record["height"],
                record["source_fps"], record["size_bytes"])
    return record


@project_locked
def delete_upload(project: Any, segment_id: Any) -> bool:
    """Remove one uploaded video and its cover. Returns True if it was there.

    The index is rewritten first and rolled back if the files refuse to go (a preview
    still open in the browser on Windows), so a failed delete never loses the record of a
    file that is still on disk.

    The cards after it move up one number: the deck is always numbered 1..N, which is what
    the user sees and what a saved workflow reads. The files keep their storage_name, so
    closing the gap writes one index and moves no bytes.
    """
    name = sanitize_project_name(project)
    if isinstance(segment_id, bool) or not isinstance(segment_id, int) or segment_id < 1:
        raise ValueError("segment_id 必须是正整数。")
    idx = load_upload_index(name)
    record = next((v for v in idx.get("videos", []) if v.get("segment_id") == segment_id), None)
    if record is None:
        return False
    files_dir = get_files_dir(name, create=False)
    paths = [os.path.join(files_dir, record.get("storage_name", "")),
             os.path.join(files_dir, record.get("thumbnail", ""))]
    # A per-record copy: _renumber() edits the records in place, and the rollback has to
    # hold the numbers as they were before the gap closed.
    previous = dict(idx)
    previous["videos"] = [dict(v) for v in idx.get("videos", [])]
    kept = [v for v in idx.get("videos", []) if v.get("segment_id") != segment_id]
    idx["videos"] = _renumber(sorted(kept, key=_order_key))
    _write_index(name, idx)
    try:
        for path in paths:
            if path and os.path.isfile(path):
                os.remove(path)  # Never hide permission / in-use errors from the UI.
    except OSError:
        _write_index(name, previous)
        raise
    logger.info("[H3 LVM Uploads] Deleted '%s' #%s from '%s'",
                record.get("original_name"), segment_id, name)
    return True


@project_locked
def reorder_uploads(project: Any, ordered_ids: Any) -> Dict[str, Any]:
    """Rewrite the order of one project's cards - and with it the numbering.

    The number is how a workflow reaches a card, so the order the user arranges in the
    panel has to be the order the ids count in: the first card becomes segment_id 1.
    The files keep the opaque names they were given at import and every read goes
    through the record, so a reorder writes one index and moves no bytes.

    The list must be exactly the current cards in a new order. A missing id would drop a
    card silently and an id from another tab's view would move the wrong video, so both
    are refused instead of guessed at.
    """
    name = sanitize_project_name(project)
    idx = load_upload_index(name)
    videos = sorted(idx.get("videos", []), key=_order_key)
    current = [v.get("segment_id") for v in videos]
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in current):
        raise ValueError("索引里有卡片没有有效编号，请先修复或删除这张卡片，再排序。")
    current = [int(value) for value in current]
    if not isinstance(ordered_ids, list):
        raise ValueError("新的顺序必须是一串编号。")
    wanted: List[int] = []
    for value in ordered_ids:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("顺序里的编号必须是正整数。")
        wanted.append(int(value))
    if len(set(wanted)) != len(wanted):
        raise ValueError("新的顺序里有重复的编号，请刷新后重试。")
    if sorted(wanted) != current:
        raise ValueError("新的顺序和当前的卡片对不上（也许另一个标签页刚改过），请刷新后重试。")
    if wanted == current:
        # Nothing moved: no write, so the index does not look changed in a diff.
        return {"project": name, "order": current, "videos": len(current)}
    by_id = {int(v["segment_id"]): v for v in videos}
    ordered = _renumber([by_id[asset_id] for asset_id in wanted])
    # next_id is the storage counter, not a card number: it only ever moves up, so a file
    # name is never reused even after a delete closed a gap.
    idx["videos"] = ordered
    idx["project_name"] = name
    idx["schema_version"] = SCHEMA_VERSION
    idx["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_index(name, idx)
    logger.info("[H3 LVM Uploads] Reordered %d cards in '%s'", len(ordered), name)
    return {"project": name, "order": [int(v["segment_id"]) for v in ordered],
            "videos": len(ordered)}


def _remove_quietly(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        logger.warning("[H3 LVM Uploads] Could not remove leftover file %s", path)


__all__ = [
    "ALLOWED_SUFFIXES", "BIN_DIR_NAME", "BROWSER_PLAYABLE", "COVER_SUFFIX", "DEFAULT_PROJECT",
    "INDEX_NAME", "MAX_SEGMENT_ID", "MAX_UPLOAD_BYTES", "SCHEMA_VERSION",
    "checked_upload_file", "count_uploads", "create_upload_project", "delete_upload",
    "delete_upload_project", "find_upload", "get_base_dir", "get_files_dir", "get_project_dir",
    "import_upload", "index_path", "list_upload_projects", "list_uploads", "load_upload_index",
    "open_partial", "reorder_uploads", "resolve_upload", "safe_suffix", "set_base_dir_override",
]
