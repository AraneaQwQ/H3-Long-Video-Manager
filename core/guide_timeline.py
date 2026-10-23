"""Guide list for the H3 Guide Timeline node (pure: parsing, validation, ordering).

Why this is a separate module: the node is the only place that touches files, VAEs
and torch, and everything that decides *whether a set of guides is legal* has to be
readable and testable without any of that. The frontend mirrors these rules in
web/guide_state.js so the card deck and the timeline say the same thing the node
will; if a rule changes here, change it there in the same commit.

What a guide is: one media asset (an image or an audio) plus the frame of the
target video it is anchored to. The native MiniMaxH3AddGuide anchors one guide per
call and chains, so a guide list is exactly "the chain the user would have wired",
kept in one widget so it survives save / reload / API queue like any other value.

frame_index is the authoritative time position (the native node's frame_idx).
Seconds are only ever a display and an input form: fps is the native constant 24,
so seconds <-> frames is a division the UI does, never something we store.

Two states keep a guide out of the run and out of the quota, and both are the
user's own doing rather than a silent deletion:

  enabled: false   the card is parked (停用) - it stays in the list, visible.
  frame_index: null the card holds media but is not on the timeline (待放置).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import uuid

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# comfy_extras/nodes_minimax_h3.py: FPS = 24. There is no fps widget on purpose:
# the native model has one fixed rate, so a second number could only ever disagree.
DEFAULT_FPS = 24

# First-version product limits, not an official model limit. Parked and unplaced
# cards do not count: they never reach the encoder.
MAX_GUIDE_IMAGES = 16
MAX_GUIDE_AUDIOS = 16
MAX_GUIDE_TOTAL = 32

# comfy/ldm/minimax/model.py:30 - how many pixel frames one video latent token
# stands for. Mirrored here so the range can be checked without torch; the node
# reads the real table from ComfyUI and passes it in, so the two cannot drift.
FRAME_PER_TOKEN = (1, 4, 4, 4, 4)

IMAGE_KIND = "image"
AUDIO_KIND = "audio"
KINDS = (IMAGE_KIND, AUDIO_KIND)

# Same three folders ComfyUI serves through /view, and the same rule as
# core/ref_media.py: a relative path inside one of them, never an absolute one.
ALLOWED_MEDIA_TYPES = ("input", "output", "temp")

LABEL_RE = re.compile(r"^(IMG|AUD)-(\d{2,})$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
IMAGE_EXT = re.compile(r"\.(png|jpe?g|jfif|webp|bmp|gif|tif|tiff)$", re.IGNORECASE)
AUDIO_EXT = re.compile(r"\.(wav|mp3|m4a|aac|ogg|oga|flac|opus|webm)$", re.IGNORECASE)


def media_kind(filename) -> str:
    """"audio" / "image" / "other" by extension - the same table as ref_media.py."""
    name = str(filename or "")
    if AUDIO_EXT.search(name):
        return "audio"
    if IMAGE_EXT.search(name):
        return "image"
    return "other"


def label_for(kind: str, index: int) -> str:
    """The card label: IMG-01 / AUD-01. Display only; the id is the identity."""
    prefix = "AUD" if kind == AUDIO_KIND else "IMG"
    return f"{prefix}-{index + 1:02d}"


# --- Time ---
def frame_count_from_latent_t(latent_t: int, frame_per_token=FRAME_PER_TOKEN) -> int:
    """Pixel frames an H3 video latent of ``latent_t`` tokens holds.

    The native Add Guide node computes it the same way (nodes_minimax_h3.py:200).
    latent_t 2 is the 5-frame minimum, then every 5 tokens is 20 more frames.
    """
    if latent_t is None or int(latent_t) <= 0:
        return 0
    table = tuple(frame_per_token) or FRAME_PER_TOKEN
    return sum(table[k % len(table)] for k in range(int(latent_t)))


def guide_frames_for(image_frames: int) -> int:
    """How many frames the native node keeps from an image batch.

    A batch shorter than 5 frames is a single image; a longer one is a clip and is
    cropped down to the model's valid clip lengths (5, 22, 39... = 17n+5).
    """
    count = int(image_frames or 1)
    if count < 5:
        return 1
    while count % 17 != 5:
        count -= 1
    return max(count, 1)


def frame_to_seconds(frame_index, fps: int = DEFAULT_FPS) -> float:
    if frame_index is None:
        return 0.0
    return int(frame_index) / float(fps or DEFAULT_FPS)


def seconds_to_frame(seconds, fps: int = DEFAULT_FPS) -> int:
    """Round to the nearest frame - the UI writes frames, never seconds."""
    return int(round(float(seconds or 0.0) * float(fps or DEFAULT_FPS)))


def align_frame_count(frames: int) -> int:
    """Round a frame count up to the next 17n+5, the only length H3 accepts.

    This is the native node's own rule (comfy_extras/nodes_minimax_h3.py:
    align_frame_count), copied rather than imported so the editor's ruler and the
    executed latent can never disagree about which number they are talking about.
    """
    count = max(5, int(frames))
    while count % 17 != 5:
        count += 1
    return count


def frames_from_seconds(seconds, fps: int = DEFAULT_FPS) -> int:
    """Seconds typed by a user -> the frame count an H3 run would produce.

    The same arithmetic as the native node: max(5, round(seconds * fps)) rounded up
    to 17n+5, so 3.0s @ 24fps is 72 -> 73 frames and 10.0s is 240 -> 243 frames.
    A blank or non-positive value means "not set" and returns 0.
    """
    try:
        value = float(seconds or 0.0)
    except (TypeError, ValueError):
        return 0
    if not value > 0:
        return 0
    return align_frame_count(max(5, int(round(value * float(fps or DEFAULT_FPS)))))


def audio_span_frames(sample_count: int, sample_rate: int, fps: int = DEFAULT_FPS) -> float:
    """How many pixel frames an audio guide covers, in float frame space.

    The native node resamples to the audio VAE's rate internally, so the span only
    depends on the source's own sample count and rate.
    """
    if not sample_count or not sample_rate:
        return 0.0
    return max(0, int(sample_count)) / float(sample_rate) * float(fps or DEFAULT_FPS)


# --- One guide ---
def _clean_id(value, seen: set) -> str:
    raw = str(value or "")
    if ID_RE.match(raw) and raw not in seen:
        seen.add(raw)
        return raw
    # A duplicate or a malformed id is not the user's problem to fix: the identity
    # exists so a rename or a delete cannot re-point a card at another one's media.
    while True:
        fresh = uuid.uuid4().hex[:16]
        if fresh not in seen:
            seen.add(fresh)
            return fresh


def _clean_asset(value, index: int) -> dict:
    if isinstance(value, str):
        value = {"filename": value}
    if not isinstance(value, dict):
        raise ValueError(f"guide {index} has no media file")
    filename = str(value.get("filename") or "").strip().replace("\\", "/")
    if not filename:
        raise ValueError(f"guide {index} has no media file")
    if os.path.isabs(filename) or filename.startswith("/") or ".." in filename.split("/"):
        raise ValueError(f"guide {index} must be a path inside the media folder, got: {filename}")
    if os.path.basename(filename).startswith("."):
        raise ValueError(f"guide {index} has a hidden file name: {filename}")
    kind = str(value.get("type") or "input")
    if kind not in ALLOWED_MEDIA_TYPES:
        raise ValueError(f"guide {index} has an unknown media folder: {kind}")
    return {"filename": filename, "subfolder": str(value.get("subfolder") or ""), "type": kind}


def _clean_sample(value, index: int, field: str) -> int:
    """A sample position: a whole number of samples, not seconds."""
    if value is None or value == "":
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"guide {index} has a non-numeric {field}: {value!r}")
    try:
        number = float(value) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        raise ValueError(f"guide {index} has a non-numeric {field}: {value!r}")
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"guide {index} has an invalid {field}: {value!r}")
    return int(round(number))


def _clean_guide(item, index: int, seen_ids: set) -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"guide {index} is not an object")
    kind = str(item.get("kind") or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"guide {index} has an unknown kind: {item.get('kind')!r}")

    frame_index = item.get("frame_index", item.get("frame_idx"))
    if frame_index is None or frame_index == "":
        frame_index = None  # 待放置: the card holds media but is not on the timeline
    else:
        try:
            frame_index = int(frame_index)
        except (TypeError, ValueError):
            raise ValueError(f"guide {index} has a non-numeric frame_index: {frame_index!r}")
        if frame_index < 0:
            # The native node counts negative frame_idx from the end, but a card
            # that moved itself off the left edge is a bug the user cannot see.
            raise ValueError(f"guide {index} has a negative frame_index: {frame_index}")

    guide = {
        "id": _clean_id(item.get("id"), seen_ids),
        "kind": kind,
        "label": str(item.get("label") or "").strip() or None,
        "enabled": bool(item.get("enabled", True)),
        "frame_index": frame_index,
        "asset": _clean_asset(item.get("asset", item.get("filename")), index),
    }
    if kind == AUDIO_KIND:
        guide["source_start_sample"] = _clean_sample(item.get("source_start_sample"), index, "source_start_sample")
        guide["source_end_sample"] = _clean_sample(item.get("source_end_sample"), index, "source_end_sample")
        rate = item.get("sample_rate")
        guide["sample_rate"] = int(rate) if rate else 0
    return guide


def parse_guides(raw, max_total: int = MAX_GUIDE_TOTAL) -> list:
    """Return an ordered list of normalised guides.

    Accepts the JSON the panel writes ({"guides": [...]} or a bare list), a plain
    Python list (a hand-written API prompt), or nothing at all. Anything malformed
    is an error the user can read, not a silent drop. Over the quota is an error
    too: a guide that quietly disappeared from a 40-card list is worse than a
    message that says which one.
    """
    if raw is None:
        data = []
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            data = []
        else:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"guides is not valid JSON: {exc.msg} (position {exc.pos})")
    elif isinstance(raw, (list, tuple, dict)):
        data = raw
    else:
        raise ValueError("guides must be a JSON list of guide objects")

    if isinstance(data, dict):
        data = data.get("guides", [])
    if isinstance(data, tuple):
        data = list(data)
    if not isinstance(data, list):
        raise ValueError("guides must be a JSON list of guide objects")

    seen_ids: set = set()
    guides = [_clean_guide(item, index, seen_ids) for index, item in enumerate(data)]
    ensure_labels(guides)

    running = {IMAGE_KIND: 0, AUDIO_KIND: 0}
    for guide in guides:
        if not is_runnable(guide):
            continue
        running[guide["kind"]] += 1
    over = []
    if running[IMAGE_KIND] > MAX_GUIDE_IMAGES:
        over.append(f"启用的图片 Guide 有 {running[IMAGE_KIND]} 个，最多 {MAX_GUIDE_IMAGES} 个")
    if running[AUDIO_KIND] > MAX_GUIDE_AUDIOS:
        over.append(f"启用的音频 Guide 有 {running[AUDIO_KIND]} 个，最多 {MAX_GUIDE_AUDIOS} 个")
    if sum(running.values()) > max_total:
        over.append(f"启用的 Guide 合计 {sum(running.values())} 个，最多 {max_total} 个")
    if over:
        raise ValueError("；".join(over))
    return guides


def ensure_labels(guides: list) -> list:
    """Keep the IMG-xx / AUD-xx the user already sees; only fill in what is missing.

    The label is display-only (the id is the identity), but it is also what every
    validation message and every lane marker names. Re-numbering by list position
    meant that deleting one card renamed all the later ones, so a message about
    "IMG-03" could point at a different card after the next click. A label that is
    already well-formed stays; a card without one (a fresh import, a copy, an
    external merge) gets the smallest free number of its kind.
    """
    taken: set = set()
    for guide in guides:
        label = str(guide.get("label") or "").strip().upper()
        if LABEL_RE.match(label) and label not in taken:
            guide["label"] = label
            taken.add(label)
        else:
            guide["label"] = None
    for guide in guides:
        if guide["label"]:
            continue
        index = 0
        while label_for(guide["kind"], index) in taken:
            index += 1
        guide["label"] = label_for(guide["kind"], index)
        taken.add(guide["label"])
    return guides



def serialize_guides(guides: list, extra: dict | None = None) -> str:
    """The widget value. Key order is fixed so an unchanged list is not a diff."""
    document = {"schema_version": SCHEMA_VERSION, "fps": DEFAULT_FPS, "guides": []}
    for guide in guides:
        entry = {
            "id": guide["id"],
            "kind": guide["kind"],
            "label": guide.get("label") or label_for(guide["kind"], 0),
            "enabled": bool(guide.get("enabled", True)),
            "frame_index": guide.get("frame_index"),
            "asset": {
                "filename": guide["asset"]["filename"],
                "subfolder": guide["asset"].get("subfolder", ""),
                "type": guide["asset"].get("type", "input"),
            },
        }
        if guide["kind"] == AUDIO_KIND:
            entry["source_start_sample"] = int(guide.get("source_start_sample") or 0)
            entry["source_end_sample"] = int(guide.get("source_end_sample") or 0)
            entry["sample_rate"] = int(guide.get("sample_rate") or 0)
        document["guides"].append(entry)
    for key, value in (extra or {}).items():
        if key not in document:
            document[key] = value
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def execution_digest(guides: list) -> str:
    """What the run depends on: order, media, placement, trim, enabled.

    Deliberately not the whole widget value - selecting a card or changing the
    timeline zoom must not make the model re-encode anything.
    """
    digest = hashlib.sha256()
    for guide in guides:
        digest.update(
            "|{kind}|{enabled}|{frame}|{type}|{subfolder}|{filename}|{start}|{end}".format(
                kind=guide["kind"],
                enabled=int(bool(guide.get("enabled", True))),
                frame=guide.get("frame_index"),
                type=guide["asset"].get("type", "input"),
                subfolder=guide["asset"].get("subfolder", ""),
                filename=guide["asset"]["filename"],
                start=guide.get("source_start_sample", 0),
                end=guide.get("source_end_sample", 0),
            ).encode("utf-8")
        )
    return digest.hexdigest()


# --- Which guides run ---
def is_runnable(guide) -> bool:
    """Enabled and on the timeline. Anything else is kept but never encoded."""
    return bool(guide.get("enabled", True)) and guide.get("frame_index") is not None


def runnable_guides(guides: list) -> list:
    return [guide for guide in guides if is_runnable(guide)]


def parked_guides(guides: list) -> list:
    return [guide for guide in guides if not is_runnable(guide)]


def count_runnable(guides: list) -> dict:
    """{image: n, audio: n} of what would actually be encoded."""
    counts = {IMAGE_KIND: 0, AUDIO_KIND: 0}
    for guide in runnable_guides(guides):
        counts[guide["kind"]] += 1
    return counts


def sort_for_execution(guides: list) -> list:
    """The one order a set of guides always runs in.

    PackedLayout walks the keyframe list in order (comfy/ldm/minimax/model.py:377),
    so two workflows that placed the same guides at the same frames have to produce
    the same list to be equivalent. Images go first at the same frame because that
    is the fixed order this node documents.
    """
    order = {IMAGE_KIND: 0, AUDIO_KIND: 1}
    ranked = sorted(
        ((index, guide) for index, guide in enumerate(guides) if is_runnable(guide)),
        key=lambda pair: (pair[1]["frame_index"], order[pair[1]["kind"]], pair[0]),
    )
    return [guide for _, guide in ranked]


# --- Validation ---
def find_audio_overlaps(guides: list, spans: dict) -> list:
    """Pairs of audio guides whose [start, end) frame ranges intersect.

    Half-open on purpose: one audio ending at frame 48 and another starting at 48
    are back to back, which is what a user means by "接着放". ``spans`` maps a guide
    id to its length in frames, because only the caller (the node after decoding,
    the panel after an AudioContext decode) knows the real sample rate.
    """
    windows = []
    for guide in guides:
        if not is_runnable(guide) or guide["kind"] != AUDIO_KIND:
            continue
        start = float(guide["frame_index"])
        end = start + float(spans.get(guide["id"], 0.0))
        if end <= start:
            continue
        windows.append((start, end, guide))
    overlaps = []
    for first in range(len(windows)):
        for second in range(first + 1, len(windows)):
            a_start, a_end, a = windows[first]
            b_start, b_end, b = windows[second]
            if a_start < b_end and b_start < a_end:
                overlaps.append((a, b, (max(a_start, b_start), min(a_end, b_end))))
    return overlaps


def validate_guides(guides: list, frame_count: int, spans: dict | None = None,
                    image_frames: dict | None = None, fps: int = DEFAULT_FPS) -> list:
    """Every reason this list cannot run, as messages the user can act on.

    Checked before anything is encoded on purpose: finding out at guide 32 that
    guide 4 was off the end of the video has already cost a VAE encode each.
    """
    spans = spans or {}
    image_frames = image_frames or {}
    errors = []
    if frame_count <= 0:
        return ["上游没有给出可用的 H3 AV latent，无法确定视频总帧数。"]

    runnable = runnable_guides(guides)
    counts = count_runnable(guides)

    for guide in runnable:
        frame = int(guide["frame_index"])
        held = int(image_frames.get(guide["id"], 1) or 1) if guide["kind"] == IMAGE_KIND else 1
        if frame < 0 or frame >= frame_count:
            errors.append(
                f"{guide['label']} 在第 {frame} 帧（{(frame / float(fps)):.3f} 秒），"
                f"超出视频范围 0–{frame_count - 1} 帧。")
            continue
        if guide["kind"] == IMAGE_KIND and frame + guide_frames_for(held) > frame_count:
            errors.append(
                f"{guide['label']} 是一段 {guide_frames_for(held)} 帧的片段，放在第 {frame} 帧放不下"
                f"（视频只有 {frame_count} 帧）。")
        if guide["kind"] == AUDIO_KIND:
            start = int(guide.get("source_start_sample") or 0)
            end = int(guide.get("source_end_sample") or 0)
            if end and end <= start:
                errors.append(f"{guide['label']} 的裁切区间是空的：起点 {start} 采样点已经在终点 {end} 之后。")
            if frame + float(spans.get(guide["id"], 0.0)) > frame_count + 1e-6:
                errors.append(
                    f"{guide['label']} 从第 {frame} 帧开始，音频长 "
                    f"{frame_to_seconds(frame + spans.get(guide['id'], 0.0), fps):.3f} 秒，超出视频结尾。")

    seen_frames = {}
    for guide in runnable:
        if guide["kind"] != IMAGE_KIND:
            continue
        frame = int(guide["frame_index"])
        if frame in seen_frames:
            errors.append(
                f"{seen_frames[frame]['label']} 和 {guide['label']} 都在第 {frame} 帧："
                "同一帧只能锚一张图片，请错开时间。")
        else:
            seen_frames[frame] = guide

    for first, second, window in find_audio_overlaps(runnable, spans):
        errors.append(
            f"{first['label']} 和 {second['label']} 在 "
            f"{int(math.floor(window[0]))}–{int(math.ceil(window[1]))} 帧重叠：音频 Guide 不能互相覆盖。")

    if counts[IMAGE_KIND] > MAX_GUIDE_IMAGES:
        errors.append(f"启用的图片 Guide 有 {counts[IMAGE_KIND]} 个，最多 {MAX_GUIDE_IMAGES} 个。")
    if counts[AUDIO_KIND] > MAX_GUIDE_AUDIOS:
        errors.append(f"启用的音频 Guide 有 {counts[AUDIO_KIND]} 个，最多 {MAX_GUIDE_AUDIOS} 个。")
    if len(runnable) > MAX_GUIDE_TOTAL:
        errors.append(f"启用的 Guide 合计 {len(runnable)} 个，最多 {MAX_GUIDE_TOTAL} 个。")
    return errors


def summary(guides: list, frame_count: int = 0, fps: int = DEFAULT_FPS) -> dict:
    """What the node body and the editor header show. frame_count 0 means 未执行."""
    counts = count_runnable(guides)
    return {
        "images": counts[IMAGE_KIND],
        "audios": counts[AUDIO_KIND],
        "parked": len(parked_guides(guides)),
        "fps": int(fps),
        "frame_count": int(frame_count or 0),
        "duration_seconds": (int(frame_count or 0) / float(fps or DEFAULT_FPS)),
    }


def merge_guides(local: list, external) -> list:
    """Local list first, then an external guide_list, with the source marked.

    Kept as the internal half of the guide_list contract: there is no node that
    produces a guide_list yet, so the node does not advertise the socket. The merge
    point exists so adding one later does not change this node's rules - external
    entries are read-only copies here, and every cross-source check above still runs.
    """
    merged = [dict(guide, source="local") for guide in local]
    for guide in external or []:
        entry = dict(guide)
        entry["source"] = "external"
        merged.append(entry)
    return merged


# --- Media identity for the cache key ---
def guide_paths(guides: list) -> list:
    """The asset references, in list order, for resolve_media_path()/fingerprinting."""
    return [dict(guide["asset"]) for guide in guides if guide.get("asset")]


def guide_fingerprint(guides: list, roots: dict) -> str:
    """Cache key: the guide list plus the real bytes behind each asset.

    Replacing a file under the same name changes mtime/size, so the node re-runs
    instead of handing back the previous encode. Same shape as
    core/ref_media.media_fingerprint, but the trim is in sample points here.
    """
    digest = hashlib.sha256()
    for guide in guides:
        asset = guide["asset"]
        digest.update(
            "|{kind}|{enabled}|{frame}|{type}|{subfolder}|{filename}|{start}|{end}".format(
                kind=guide["kind"],
                enabled=int(bool(guide.get("enabled", True))),
                frame=guide.get("frame_index"),
                type=asset.get("type", "input"),
                subfolder=asset.get("subfolder", ""),
                filename=asset["filename"],
                start=guide.get("source_start_sample", 0),
                end=guide.get("source_end_sample", 0),
            ).encode("utf-8")
        )
        try:
            from .ref_media import resolve_media_path  # local import: keeps this module torch-free

            stat = os.stat(resolve_media_path(roots, asset))
            digest.update(f"|{stat.st_size}|{stat.st_mtime_ns}".encode("ascii"))
        except (OSError, ValueError):
            # A missing file is reported by validate_inputs; the cache key must not crash first.
            digest.update(b"|missing")
    return digest.hexdigest()