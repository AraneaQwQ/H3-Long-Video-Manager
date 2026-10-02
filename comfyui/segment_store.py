"""H3 Long Video Manager — Segment Bin storage layer (Phase A).

Saves each cut segment as a lossless tensor bundle + first-frame cover PNG +
optional MP4 preview into a per-project folder under the ComfyUI output
directory, and provides list/load access for the Picker node.

Layout (under the ComfyUI output directory):

    h3-lvm/
      <project>/
        h3lvm_index.json        # project manifest (list of saved segments)
        seg01/
          seg01.safetensors     # {video [F,H,W,C] i8|f16, audio [1,C,S] f32, sample_rate, fps}
          seg01_first.png       # first-frame cover (card thumbnail)
          seg01.mp4             # optional playable preview (only if requested)
        seg02/
          ...

Namespace isolation:
- Folder prefix ``h3-lvm`` (clipstream uses ``h3-clipstream``).
- Index file ``h3lvm_index.json`` (clipstream uses ``.bin_index.json``).
- No shared module names with clipstream.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from functools import wraps
import inspect
from .asset_paths import checked_asset_dir, preview_url
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import torch

logger = logging.getLogger(__name__)

BIN_DIR_NAME = "h3-lvm"
INDEX_NAME = "h3lvm_index.json"
DEFAULT_PROJECT = "H3_LVM"
MAX_PROJECT_NAME_LENGTH = 80

_base_dir_override: Optional[str] = None
_project_locks: Dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def set_base_dir_override(path: Optional[str]) -> None:
    """Tests only: redirect the bin base dir (e.g. a temp folder)."""
    global _base_dir_override
    _base_dir_override = path


def get_base_dir() -> str:
    if _base_dir_override:
        return _base_dir_override
    try:
        import folder_paths
        out = folder_paths.get_output_directory()
    except Exception:
        out = os.path.join(".", "output")
    return os.path.join(out, BIN_DIR_NAME)


def sanitize_project_name(name: Any) -> str:
    s = "" if name is None else str(name).strip()
    if not s:
        s = DEFAULT_PROJECT
    s = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", s)
    s = s.strip().strip(".")
    if not s:
        s = DEFAULT_PROJECT
    return s


def resolve_project(name: Any) -> str:
    return sanitize_project_name(name)


def get_project_dir(project: Any, create: bool = True) -> str:
    base = get_base_dir()
    pdir = os.path.join(base, sanitize_project_name(project))
    if create:
        os.makedirs(pdir, exist_ok=True)
    return pdir


def _project_lock(name: str):
    name = os.path.normcase(os.path.realpath(get_project_dir(name, create=False)))
    with _locks_guard:
        lock = _project_locks.get(name)
        if lock is None:
            lock = threading.RLock()
            _project_locks[name] = lock
        return lock


# ---------------------------------------------------------------------------
# Tensor helpers
# ---------------------------------------------------------------------------

def project_locked(fn):
    signature = inspect.signature(fn)
    @wraps(fn)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        with _project_lock(sanitize_project_name(bound.arguments["project"])):
            return fn(*args, **kwargs)
    return wrapped


def _write_index(project, idx):
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


def tensor_to_pil(frame: torch.Tensor):
    """Convert [H,W,C] or [1,H,W,C] float [0,1] tensor to PIL RGB Image."""
    from PIL import Image
    if frame.ndim == 4:
        frame = frame[0]
    if frame.ndim == 3 and frame.shape[0] in (1, 3, 4) and frame.shape[2] not in (1, 3, 4):
        frame = frame.permute(1, 2, 0)
    if frame.shape[-1] == 4:
        frame = frame[..., :3]
    arr = frame.detach().clamp(0, 1).mul(255).to(torch.uint8).contiguous().cpu().numpy()
    return Image.fromarray(arr)


def _save_tensors(tensors: Dict[str, torch.Tensor], path: str) -> str:
    """Save tensors via safetensors (preferred) with torch.save fallback.

    Returns the actual filename written (basename).
    """
    try:
        from safetensors.torch import save_file
        save_file(tensors, path)
        return os.path.basename(path)
    except Exception as e:
        alt = path.replace(".safetensors", ".pt") if path.endswith(".safetensors") else path + ".pt"
        torch.save(tensors, alt)
        logger.info("[H3 LVM] safetensors failed (%s); used torch.save -> %s", e, os.path.basename(alt))
        return os.path.basename(alt)


def _load_tensors(path: str) -> Dict[str, torch.Tensor]:
    if path.endswith(".safetensors"):
        try:
            from safetensors.torch import load_file
            return load_file(path)
        except Exception:
            pass
    return torch.load(path, map_location="cpu")


def _encode_mp4(images: torch.Tensor, audio: Optional[Dict[str, Any]], fps: int, out_path: str) -> bool:
    """Best-effort MP4 encode via ffmpeg (rawvideo stdin pipe + optional WAV audio)."""
    if images is None or not isinstance(images, torch.Tensor) or images.ndim != 4 or len(images) == 0:
        return False
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.warning("[H3 LVM] ffmpeg not found in PATH; skipping mp4 preview.")
        return False
    N, H, W, _C = images.shape
    if W % 2:
        W -= 1
    if H % 2:
        H -= 1
    imgs = images[:, :H, :W, :]
    try:
        raw = imgs.detach().clamp(0, 1).mul(255).to(torch.uint8).contiguous().cpu().numpy().tobytes()
    except Exception as e:
        logger.warning("[H3 LVM] mp4 raw-bytes extraction failed: %s", e)
        return False

    temp_wav = None
    cmd = [ffmpeg_bin, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
           "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(fps), "-i", "-"]

    if audio and isinstance(audio, dict) and "waveform" in audio:
        try:
            wf = audio["waveform"]
            sr = int(audio.get("sample_rate", 44100))
            if isinstance(wf, torch.Tensor) and wf.ndim >= 2:
                if wf.ndim == 3:
                    wf = wf[0]
                ch = wf.shape[0]
                pcm = wf.clamp(-1, 1).mul(32767).to(torch.int16).t().contiguous().cpu()
                ab = pcm.numpy().tobytes()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    temp_wav = tf.name
                with wave.open(temp_wav, "wb") as wv:
                    wv.setnchannels(ch)
                    wv.setsampwidth(2)
                    wv.setframerate(sr)
                    wv.writeframes(ab)
                cmd.extend(["-i", temp_wav, "-c:a", "aac", "-b:a", "192k", "-shortest"])
        except Exception as e:
            logger.warning("[H3 LVM] mp4 audio prep failed: %s", e)
            if temp_wav and os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass
            temp_wav = None

    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path])
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.communicate(input=raw)
        return proc.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path) > 0
    except Exception as e:
        logger.warning("[H3 LVM] mp4 encode exception: %s", e)
        return False
    finally:
        if temp_wav and os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Video tensor encoding
# ---------------------------------------------------------------------------

# int8 stores round(x * 255) - 128, which maps the 256 levels of an 8-bit frame
# exactly onto the signed range. The pipeline decodes 8-bit video (core/extraction
# divides decoded uint8 by 255), so int8 carries the same information as fp16 at
# half the bytes.
INT8_OFFSET = 128
VIDEO_DTYPES = ("int8", "fp16")


def normalize_save_dtype(value):
    """Map any user value onto the two supported encodings (default int8)."""
    s = "" if value is None else str(value).strip().lower()
    if s in ("fp16", "f16", "float16", "half"):
        return "fp16"
    return "int8"


def _encode_video(video: torch.Tensor, save_dtype: str) -> torch.Tensor:
    """Pack a float [0,1] video tensor for disk."""
    src = video.detach().cpu()
    if normalize_save_dtype(save_dtype) == "fp16":
        return src.to(torch.float16).contiguous()
    if src.dtype in (torch.float32, torch.float64):
        src = src.clamp(0.0, 1.0).mul(255.0).round().sub(INT8_OFFSET)
    return src.to(torch.int8).contiguous()


def _decode_video(tensor: torch.Tensor) -> torch.Tensor:
    """Reverse _encode_video; stored float tensors are passed through."""
    if tensor.dtype == torch.int8:
        return tensor.to(torch.float32).add(INT8_OFFSET).div(255.0).contiguous()
    if tensor.dtype == torch.uint8:
        return tensor.to(torch.float32).div(255.0).contiguous()
    return tensor

# ---------------------------------------------------------------------------
# Save / list / load
# ---------------------------------------------------------------------------

@project_locked
def save_segment(
    project: Any,
    seg_index_1based: int,
    video: torch.Tensor,
    audio: Optional[Dict[str, Any]],
    fps: int,
    save_mp4: bool = False,
    meta: Optional[Dict[str, Any]] = None,
    save_dtype: str = "int8",
) -> Dict[str, Any]:
    """Save one segment to the project folder and upsert it into the index.

    ``seg_index_1based``: 1-based segment id (seg01, seg02, ...).
    "save_dtype": "int8" (half the bytes, lossless for 8-bit sources) or "fp16"
    (the original format). Either way the loader hands back float [0,1].
    Returns the meta dict for this segment.
    """
    project = sanitize_project_name(project)
    tag = f"seg{int(seg_index_1based):02d}"
    sdir = checked_asset_dir(get_base_dir(), get_project_dir(project), tag)
    # Clean slate: remove old segment data to avoid stale files (e.g. leftover mp4)
    if os.path.isdir(sdir):
        shutil.rmtree(sdir)
    os.makedirs(sdir, exist_ok=True)

    # --- tensors (feed H3 directly; _encode_video decides the packing) ---
    video_cpu = _encode_video(video, save_dtype)
    audio_wav = None
    audio_sr = 44100
    if audio is not None:
        wf = audio.get("waveform")
        if wf is not None:
            audio_wav = wf.detach().to(torch.float32).cpu().contiguous()
            audio_sr = int(audio.get("sample_rate", 44100))

    tensors: Dict[str, torch.Tensor] = {"video": video_cpu}
    if audio_wav is not None:
        tensors["audio"] = audio_wav
    tensors["sample_rate"] = torch.tensor([audio_sr], dtype=torch.int64)
    tensors["fps"] = torch.tensor([int(fps)], dtype=torch.int64)

    tensors_file = _save_tensors(tensors, os.path.join(sdir, f"{tag}.safetensors"))

    # --- first-frame cover PNG ---
    thumbnail = ""
    try:
        thumbnail = f"{tag}_first.png"
        tensor_to_pil(video[0]).save(os.path.join(sdir, thumbnail))
    except Exception as e:
        logger.warning("[H3 LVM] first-frame cover failed for %s: %s", tag, e)
        thumbnail = ""

    # --- optional mp4 preview ---
    mp4 = ""
    if save_mp4:
        mp4_candidate = f"{tag}.mp4"
        if _encode_mp4(video, audio, int(fps), os.path.join(sdir, mp4_candidate)):
            mp4 = mp4_candidate
        else:
            logger.warning("[H3 LVM] mp4 preview skipped for %s (encoder unavailable/failed).", tag)

    # --- meta ---
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_frames = int(video.shape[0])
    seg_meta: Dict[str, Any] = {
        "segment_id": int(seg_index_1based),
        "tag": tag,
        "dir": tag,
        "frames": n_frames,
        "width": int(video.shape[2]),
        "height": int(video.shape[1]),
        "fps": int(fps),
        "duration_sec": round(n_frames / float(fps), 4) if fps else None,
        "video_dtype": normalize_save_dtype(save_dtype),
        "has_audio": audio_wav is not None,
        "sample_rate": audio_sr,
        "has_mp4": bool(mp4),
        "tensors_file": tensors_file,
        "thumbnail": thumbnail,
        "mp4": mp4,
        "saved_at": now,
    }
    if meta:
        for k, v in meta.items():
            seg_meta.setdefault(k, v)

    with _project_lock(project):
        _upsert_index(project, seg_meta)

    logger.info("[H3 LVM] saved segment %s to %s (%d frames, %dx%d, video=%s, %s)",
                tag, get_project_dir(project, create=False), n_frames,
                int(video.shape[2]), int(video.shape[1]),
                seg_meta["video_dtype"], "with mp4" if mp4 else "tensor+png")
    return seg_meta


@project_locked
def load_segment(project: Any, seg_index_1based: int) -> Tuple[torch.Tensor, Optional[Dict[str, Any]], Dict[str, Any]]:
    """Load a saved segment -> (video_tensor, audio_dict, meta)."""
    project = sanitize_project_name(project)
    tag = f"seg{int(seg_index_1based):02d}"
    sdir = os.path.join(get_project_dir(project, create=False), tag)
    if not os.path.isdir(sdir):
        raise FileNotFoundError(f"segment {seg_index_1based} dir not found at {sdir}")

    tensors = None
    for name in (f"{tag}.safetensors", f"{tag}.pt"):
        p = os.path.join(sdir, name)
        if os.path.isfile(p):
            tensors = _load_tensors(p)
            break
    if tensors is None:
        raise FileNotFoundError(f"segment {seg_index_1based} tensors not found in {sdir}")

    video = _decode_video(tensors["video"])
    audio = None
    if "audio" in tensors:
        if "sample_rate" in tensors:
            sr = int(tensors["sample_rate"].flatten()[0]) if tensors["sample_rate"].numel() else 44100
        else:
            sr = 44100
        audio = {"waveform": tensors["audio"], "sample_rate": sr}

    idx = load_project_index(project)
    meta = next((c for c in idx.get("segments", []) if c.get("segment_id") == int(seg_index_1based)), {})
    return video, audio, meta


@project_locked
def load_project_index(project: Any) -> Dict[str, Any]:
    pdir = get_project_dir(project, create=False)
    p = os.path.join(pdir, INDEX_NAME)
    empty = {"project_name": sanitize_project_name(project), "total_segments": 0, "segments": []}
    if not os.path.isfile(p):
        return empty
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("[H3 LVM] index read failed: %s", e)
        return empty
    data.setdefault("project_name", sanitize_project_name(project))
    data.setdefault("segments", [])
    data.setdefault("total_segments", len(data["segments"]))
    return data


def _upsert_index(project: str, seg_meta: Dict[str, Any]) -> None:
    pdir = get_project_dir(project, create=True)
    p = os.path.join(pdir, INDEX_NAME)
    idx: Dict[str, Any] = {"project_name": project, "total_segments": 0, "segments": []}
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                idx = json.load(f)
        except Exception:
            pass
    segs = [s for s in idx.get("segments", []) if s.get("segment_id") != seg_meta["segment_id"]]
    segs.append(seg_meta)
    segs.sort(key=lambda s: s.get("segment_id", 0))
    idx["segments"] = segs
    idx["total_segments"] = len(segs)
    idx["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    idx["project_name"] = project
    _write_index(project, idx)


@project_locked
def list_project(project: Any) -> Dict[str, Any]:
    """Return the project index enriched with /view URLs (for the frontend)."""
    project = sanitize_project_name(project)
    idx = load_project_index(project)
    pdir = get_project_dir(project, create=False)
    sub_prefix = f"{BIN_DIR_NAME}/{project}"

    for seg in idx.get("segments", []):
        d = seg.get("dir", seg.get("tag", ""))
        sub = f"{sub_prefix}/{d}"

        thumb = seg.get("thumbnail", "")
        if thumb and os.path.isfile(os.path.join(pdir, d, thumb)):
            seg["thumbnail_url"] = preview_url(os.path.join(pdir, d, thumb), sub)
        else:
            seg["thumbnail_url"] = ""

        mp4 = seg.get("mp4", "")
        if mp4 and os.path.isfile(os.path.join(pdir, d, mp4)):
            seg["mp4_url"] = preview_url(os.path.join(pdir, d, mp4), sub)
            seg["has_mp4"] = True
        else:
            seg["mp4_url"] = ""
            seg["has_mp4"] = False

    return idx


def list_projects() -> List[str]:
    base = get_base_dir()
    if not os.path.isdir(base):
        return []
    out = []
    for name in os.listdir(base):
        if os.path.isdir(os.path.join(base, name)) and os.path.isfile(os.path.join(base, name, INDEX_NAME)):
            out.append(name)
    return sorted(out)

def list_projects_with_counts() -> List[Dict[str, Any]]:
    """Lists project bins together with how many segments each one holds.

    The Picker shows these counts in its menu so a name is never chosen from memory.
    An empty bin is still a valid place to save the next shot, so nothing is filtered
    out here - the count only says what the entry points at.
    """
    out: List[Dict[str, Any]] = []
    for name in list_projects():
        segments = len(load_project_index(name).get("segments", []))
        out.append({"name": name, "segments": segments})
    return out


def create_project(project: Any) -> Dict[str, Any]:
    """Creates an empty project bin, or confirms an existing one, and reports the name.

    The Picker offers this so a new story starts in a folder chosen on purpose rather
    than whatever name the first Manager node happened to be left with. Creating is
    idempotent - an existing name is selected, not duplicated - and the name returned
    is the sanitized one the folder really uses, so the UI can never drift from disk.

    An empty index is written because ``list_projects`` only offers folders that
    already have one; without it a freshly created bin would stay invisible to the menu.
    The bin lock is held so the index write cannot race a save in the same folder.
    """
    typed = str("" if project is None else project).strip()
    if not any(c.isalnum() for c in typed):
        raise ValueError("项目名称里至少要有一个字母或数字（例如「科幻短片 01」）。")
    safe_name = sanitize_project_name(typed)
    if len(safe_name) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError("项目名称太长，请控制在 %d 个字符以内。" % MAX_PROJECT_NAME_LENGTH)
    with _project_lock(safe_name):
        existed = os.path.isdir(get_project_dir(safe_name, create=False))
        if not existed:
            _write_index(safe_name, {"project_name": safe_name, "total_segments": 0, "segments": []})
        segments = len(load_project_index(safe_name).get("segments", []))
    logger.info("[H3 LVM] %s project '%s'", "Reusing existing" if existed else "Created", safe_name)
    return {"name": safe_name, "created": not existed, "segments": segments}


def delete_project(project: Any, confirm: Any = "") -> Dict[str, Any]:
    """Deletes a whole project bin: every segment, cover and preview inside it.

    This is the mirror of ``create_project`` - same name rules, and the name that
    reaches the disk is the sanitized one. ``confirm`` has to repeat that name, which
    stops a panel left open on another bin from emptying the wrong folder when the
    user switched bins in a second tab. The bin lock is held so a shot cannot be
    saved into a folder that is being removed underneath it.
    """
    typed = str("" if project is None else project).strip()
    if not any(c.isalnum() for c in typed):
        raise ValueError("项目名称里至少要有一个字母或数字。")
    safe_name = sanitize_project_name(typed)
    if str("" if confirm is None else confirm).strip() != safe_name:
        raise ValueError("请先确认要删除的项目名称，再按删除。")
    with _project_lock(safe_name):
        base = os.path.realpath(get_base_dir())
        target = os.path.realpath(os.path.join(base, safe_name))
        if target == base or os.path.dirname(target) != base:
            raise ValueError("项目名称无效，只能删除素材库内的项目文件夹。")
        if not os.path.isdir(target):
            return {"name": safe_name, "deleted": False, "segments": 0}
        segments = len(load_project_index(safe_name).get("segments", []))
        shutil.rmtree(target)  # Never hide permission / in-use errors from the UI.
    logger.info("[H3 LVM] Deleted project '%s' (%d segments)", safe_name, segments)
    return {"name": safe_name, "deleted": True, "segments": segments}


@project_locked
def delete_segment(project: Any, seg_index_1based: int) -> bool:
    """Remove a saved segment (files + index entry). Returns True if removed."""
    project = sanitize_project_name(project)
    if isinstance(seg_index_1based, bool) or not isinstance(seg_index_1based, int) or seg_index_1based < 1:
        raise ValueError("segment_id must be a positive integer")
    tag = f"seg{seg_index_1based:02d}"
    sdir = checked_asset_dir(get_base_dir(), get_project_dir(project, create=False), tag)
    idx = load_project_index(project)
    found = any(s.get("segment_id") == seg_index_1based for s in idx.get("segments", []))
    if not found:
        return False
    previous = dict(idx)
    idx["segments"] = [s for s in idx.get("segments", []) if s.get("segment_id") != seg_index_1based]
    idx["total_segments"] = len(idx["segments"])
    idx["last_updated"] = datetime.now().isoformat()
    _write_index(project, idx)
    try:
        if os.path.exists(sdir):
            shutil.rmtree(sdir)  # Never hide permission / in-use errors from the UI.
    except OSError:
        _write_index(project, previous)
        raise
    return True


__all__ = [
    "BIN_DIR_NAME",
    "INDEX_NAME",
    "DEFAULT_PROJECT",
    "set_base_dir_override",
    "get_base_dir",
    "sanitize_project_name",
    "resolve_project",
    "get_project_dir",
    "tensor_to_pil",
    "save_segment",
    "load_segment",
    "load_project_index",
    "list_project",
    "list_projects",
    "list_projects_with_counts",
    "create_project",
    "delete_project",
    "MAX_PROJECT_NAME_LENGTH",
    "delete_segment",
]
