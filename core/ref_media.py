"""Media lists for the H3 reference loaders (pure: parsing, validation, slots).

The panel stores the ordered media as a JSON string in one hidden widget, so the
order survives save / reload / API queue exactly like any other widget value.
This module turns that string into validated entries and fills the fixed output
slots; decoding lives in the node, which is the only place that touches files.

A card may be parked ("skip": true): it stays in the list so the panel can show it
and bring it back, but active_entries() drops it before the slots are filled, so a
parked card never reaches H3 and never takes a numbered port.

An audio card may also be trimmed ("start" / "duration" in seconds): the file stays in
the list and the card still shows it, but the node hands H3 only that window. The units
and the negative-start rule are ComfyUI's own TrimAudioDuration on purpose, so a user
who has used that node already knows how this one behaves.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re

logger = logging.getLogger(__name__)

# The official MiniMaxH3ReferenceToVideo autogrows ref_image_ (max 9) and
# ref_audio_ (max 3); these are the same limits, so a slot always exists.
MAX_REF_IMAGES = 9
MAX_REF_AUDIOS = 3

# ComfyUI's three media folders. "input" is what the panel uploads into.
ALLOWED_MEDIA_TYPES = ("input", "output", "temp")

# Extension tables mirrored in web/ref_state.js (mediaKind). Only audio cards can be
# trimmed, and this is the rule that says so - an image entry with a stray "start"
# key parses exactly the way it always did.
IMAGE_EXT = re.compile(r"\.(png|jpe?g|jfif|webp|bmp|gif|tif|tiff)$", re.IGNORECASE)
AUDIO_EXT = re.compile(r"\.(wav|mp3|m4a|aac|ogg|oga|flac|opus|webm)$", re.IGNORECASE)


def media_kind(filename) -> str:
    """"audio" / "image" / "other" by extension."""
    name = str(filename or "")
    if AUDIO_EXT.search(name):
        return "audio"
    if IMAGE_EXT.search(name):
        return "image"
    return "other"


def _clean_seconds(value, index: int, field: str) -> float:
    """One trim value in seconds: a finite number, or 0.0 for "not set"."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise ValueError(f"media item {index} has a non-numeric {field}: {value!r}")
    if isinstance(value, str):
        # The panel always writes a number, but a hand-written widget list may quote one.
        try:
            number = float(value.strip())
        except ValueError:
            raise ValueError(f"media item {index} has a non-numeric {field}: {value!r}")
    elif not isinstance(value, (int, float)):
        raise ValueError(f"media item {index} has a non-numeric {field}: {value!r}")
    else:
        number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"media item {index} has a {field} that is not a finite number: {value!r}")
    return number


def _clean_filename(value, index: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"media item {index} has no filename")
    name = value.strip().replace("\\", "/")
    if not name:
        raise ValueError(f"media item {index} has an empty filename")
    if os.path.isabs(name) or name.startswith("/") or ".." in name.split("/"):
        raise ValueError(
            f"media item {index} must be a path inside the media folder, got: {value}"
        )
    if os.path.basename(name).startswith("."):
        raise ValueError(f"media item {index} has a hidden file name: {value}")
    return name


def parse_media_list(raw, max_items: int = MAX_REF_IMAGES) -> list:
    """Return an ordered list of {"filename", "subfolder", "type"} entries.

    Accepts the JSON the panel writes, a plain list of file names (hand-written
    API prompts), or nothing at all. Anything malformed is an error the user can
    read, not a silent drop.

    Parked entries are kept in the list but never counted against max_items: only
    the cards that hold a slot are limited.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"media_files is not valid JSON: {exc.msg} (position {exc.pos})")
    elif isinstance(raw, (list, tuple)):
        data = list(raw)
    else:
        raise ValueError("media_files must be a JSON list of media entries")

    if not isinstance(data, list):
        raise ValueError("media_files must be a JSON list of media entries")

    entries = []
    for index, item in enumerate(data):
        if isinstance(item, str):
            entry = {"filename": item, "subfolder": "", "type": "input"}
        elif isinstance(item, dict):
            entry = {
                "filename": item.get("filename"),
                "subfolder": item.get("subfolder") or "",
                "type": (item.get("type") or "input"),
            }
        else:
            raise ValueError(f"media item {index} must be an object or a file name")

        entry["filename"] = _clean_filename(entry["filename"], index)
        subfolder = str(entry["subfolder"]).strip().replace("\\", "/")
        if subfolder.startswith("/") or ".." in subfolder.split("/"):
            raise ValueError(f"media item {index} has an unsafe subfolder: {entry['subfolder']}")
        entry["subfolder"] = subfolder.strip("/")

        media_type = str(entry["type"]).strip().lower()
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise ValueError(
                f"media item {index} has type {entry['type']!r}; "
                f"expected one of {', '.join(ALLOWED_MEDIA_TYPES)}"
            )
        entry["type"] = media_type
        # A parked card keeps its file so the panel can bring it back, but it holds
        # no slot. Absent means active, so lists saved before this feature parse the
        # same way they always did.
        entry["skip"] = bool(item.get("skip", False)) if isinstance(item, dict) else False
        if not entry["skip"]:
            del entry["skip"]
        # Trim is seconds, and only audio cards have it. Absent or zero means the whole
        # file, and a list saved before this feature parses byte-for-byte as before.
        if media_kind(entry["filename"]) == "audio":
            start = _clean_seconds(item.get("start"), index, "start") if isinstance(item, dict) else 0.0
            length = _clean_seconds(item.get("duration"), index, "duration") if isinstance(item, dict) else 0.0
            if length < 0:
                raise ValueError(f"media item {index} has a negative duration: {length}")
            if start:
                entry["start"] = start
            if length:
                entry["duration"] = length
        entries.append(entry)

    # Only the cards that hold a slot are limited; dropping a parked card would
    # silently delete something the user chose to keep.
    kept = []
    used = 0
    truncated = 0
    for entry in entries:
        if is_skipped(entry):
            kept.append(entry)
            continue
        if used >= max_items:
            truncated += 1
            continue
        used += 1
        kept.append(entry)
    if truncated:
        logger.warning("[H3 Ref Loader] %d cards hold a slot but only %d exist: %d ignored",
                       used + truncated, max_items, truncated)
    return kept


def is_skipped(entry) -> bool:
    """True for a parked card: it is in the list but holds no slot."""
    return bool(entry.get("skip")) if isinstance(entry, dict) else False


def split_entries(entries: list) -> tuple:
    """(active, parked) in list order - the same split the card deck draws."""
    active, parked = [], []
    for entry in entries:
        (parked if is_skipped(entry) else active).append(entry)
    return active, parked


def active_entries(entries: list) -> list:
    """The cards that fill ref_image_ / ref_audio_; parked cards never get there."""
    return split_entries(entries)[0]


def trim_range(entry: dict) -> tuple:
    """(start, duration) in seconds for one entry; (0.0, 0.0) is the whole file."""
    if not isinstance(entry, dict):
        return (0.0, 0.0)
    return (float(entry.get("start") or 0.0), float(entry.get("duration") or 0.0))


def trim_audio(audio: dict, start: float = 0.0, duration: float = 0.0) -> dict:
    """Cut an AUDIO dict to a time window, keeping the sample rate and channels.

    The same math as ComfyUI's TrimAudioDuration: a negative start counts back from the
    end of the file, and a zero duration runs to the end. Both ends are clamped into
    the file, so a window that reaches past it is not an error - only a window with no
    samples in it is, and that one says so in the message the user actually reads.
    """
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    total = int(waveform.shape[-1])

    first = total + int(round(float(start) * sample_rate)) if start < 0 else int(round(float(start) * sample_rate))
    first = max(0, min(first, total))
    last = first + int(round(float(duration) * sample_rate)) if duration else total
    last = max(first, min(last, total))
    if last <= first:
        raise ValueError(
            "裁切后没有音频样本：开始 %s 秒已经到文件末尾（全片 %.3f 秒），请减小开始时间或改用时长的写法。"
            % (start, total / float(sample_rate))
        )
    if first == 0 and last == total:
        return audio
    return {"waveform": waveform[..., first:last], "sample_rate": sample_rate}


def resolve_media_path(roots: dict, entry: dict) -> str:
    """Resolve one entry to an existing file inside its declared folder."""
    folder = roots.get(entry["type"])
    if not folder:
        raise ValueError(f"no media folder of type {entry['type']!r} is available")

    root = os.path.realpath(folder)
    subfolder = entry.get("subfolder") or ""
    target = os.path.realpath(os.path.join(root, subfolder, entry["filename"]))
    if os.path.commonpath([root, target]) != root:
        raise ValueError(f"{entry['filename']} is outside the {entry['type']} folder")
    if not os.path.isfile(target):
        raise ValueError(f"file not found in the {entry['type']} folder: "
                         f"{os.path.join(subfolder, entry['filename']) if subfolder else entry['filename']}")
    return target


def media_fingerprint(entries: list, roots: dict, extra: str = "") -> str:
    """Cache key for the media set: order, names, and the real bytes behind them.

    Replacing a file under the same name changes mtime/size, so the node re-runs
    instead of handing back the previous decode.
    """
    digest = hashlib.sha256()
    digest.update(extra.encode("utf-8"))
    for entry in entries:
        start, length = trim_range(entry)
        digest.update(
            f"|{entry['type']}|{entry.get('subfolder', '')}|{entry['filename']}|{start}|{length}".encode("utf-8")
        )
        try:
            stat = os.stat(resolve_media_path(roots, entry))
            digest.update(f"|{stat.st_size}|{stat.st_mtime_ns}".encode("ascii"))
        except (OSError, ValueError):
            # A missing file is reported by validate_inputs; the cache key must not crash first.
            digest.update(b"|missing")
    return digest.hexdigest()


def fill_slots(entries: list, slot_count: int, build):
    """Build one value per slot; unused slots are real None, never placeholders."""
    values = []
    for index in range(slot_count):
        values.append(build(entries[index]) if index < len(entries) else None)
    return tuple(values)
