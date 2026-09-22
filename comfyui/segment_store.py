"""H3 Long Video Manager — Segment Bin storage layer (Phase A).

Saves each cut segment as a lossless tensor bundle + first-frame cover PNG +
optional MP4 preview into a per-project folder under the ComfyUI output
directory, and provides list/load access for the Picker node.

Layout (under the ComfyUI output directory):

    h3-lvm/
      <project>/
        h3lvm_index.json        # project manifest (list of saved segments)
        seg01/
          seg01.safetensors     # {video [F,H,W,C] f16, audio [1,C,S] f32, sample_rate, fps}
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
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import torch

logger = logging.getLogger(__name__)

BIN_DIR_NAME = "h3-lvm"
INDEX_NAME = "h3lvm_index.json"
DEFAULT_PROJECT = "H3_LVM"

_base_dir_override: Optional[str] = None
_project_locks: Dict[str, threading.Lock] = {}
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


def _project_lock(name: str) -> threading.Lock:
    with _locks_guard:
        lock = _project_locks.get(name)
        if lock is None:
            lock = threading.Lock()
            _project_locks[name] = lock
        return lock


# ---------------------------------------------------------------------------
# Tensor helpers
# ---------------------------------------------------------------------------

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
# Save / list / load
# ---------------------------------------------------------------------------

def save_segment(
    project: Any,
    seg_index_1based: int,
    video: torch.Tensor,
    audio: Optional[Dict[str, Any]],
    fps: int,
    save_mp4: bool = False,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Save one segment to the project folder and upsert it into the index.

    ``seg_index_1based``: 1-based segment id (seg01, seg02, ...).
    Returns the meta dict for this segment.
    """
    project = sanitize_project_name(project)
    tag = f"seg{int(seg_index_1based):02d}"
    sdir = os.path.join(get_project_dir(project), tag)
    # Clean slate: remove old segment data to avoid stale files (e.g. leftover mp4)
    if os.path.isdir(sdir):
        shutil.rmtree(sdir, ignore_errors=True)
    os.makedirs(sdir, exist_ok=True)

    # --- tensors (lossless, feed H3 directly) ---
    video_cpu = (
        video.detach().to(torch.float16).cpu().contiguous()
        if video.dtype in (torch.float32, torch.float64)
        else video.detach().cpu().contiguous()
    )
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

    logger.info("[H3 LVM] saved segment %s to %s (%d frames, %dx%d, %s)",
                tag, get_project_dir(project, create=False), n_frames,
                int(video.shape[2]), int(video.shape[1]),
                "with mp4" if mp4 else "tensor+png")
    return seg_meta


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

    video = tensors["video"]
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
    with open(p, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


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
            seg["thumbnail_url"] = f"/view?filename={thumb}&subfolder={sub}&type=output"
        else:
            seg["thumbnail_url"] = ""

        mp4 = seg.get("mp4", "")
        if mp4 and os.path.isfile(os.path.join(pdir, d, mp4)):
            seg["mp4_url"] = f"/view?filename={mp4}&subfolder={sub}&type=output"
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


def delete_segment(project: Any, seg_index_1based: int) -> bool:
    """Remove a saved segment (files + index entry). Returns True if removed."""
    import shutil as _sh
    project = sanitize_project_name(project)
    tag = f"seg{int(seg_index_1based):02d}"
    sdir = os.path.join(get_project_dir(project, create=False), tag)
    if not os.path.isdir(sdir):
        return False
    with _project_lock(project):
        _sh.rmtree(sdir, ignore_errors=True)
        idx = load_project_index(project)
        idx["segments"] = [s for s in idx.get("segments", []) if s.get("segment_id") != int(seg_index_1based)]
        idx["total_segments"] = len(idx["segments"])
        p = os.path.join(get_project_dir(project, create=True), INDEX_NAME)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
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
    "delete_segment",
]
