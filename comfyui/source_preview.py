"""Short-lived, read-only preview tickets for explicitly selected source videos."""
from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import subprocess
import threading
import time

import folder_paths

from .video_decode import probe_video
from .video_loader_node import resolve_video_path
from .uploaded_video_store import resolve_upload

PREVIEW_TTL_SECONDS = 2 * 60 * 60
MAX_PREVIEW_TICKETS = 64
PROXY_MAX_SIDE = 1280
PROXY_FORMAT_VERSION = 1
PROXY_RECOMMENDED_CODECS = {"hevc", "h265"}

_lock = threading.RLock()
_tickets = {}
_proxy_locks = {}


def _purge(now):
    expired = [token for token, item in _tickets.items() if item["expires"] <= now]
    for token in expired:
        _tickets.pop(token, None)
    while len(_tickets) >= MAX_PREVIEW_TICKETS:
        oldest = min(_tickets, key=lambda token: _tickets[token]["created"])
        _tickets.pop(oldest, None)


def _create_path_preview(path):
    path = os.path.realpath(path)
    info = probe_video(path)
    now = time.monotonic()
    token = secrets.token_urlsafe(32)
    with _lock:
        _purge(now)
        _tickets[token] = {
            "path": path,
            "created": now,
            "expires": now + PREVIEW_TTL_SECONDS,
        }
    return {
        "url": f"/h3_lvm/source_preview?ticket={token}",
        "proxy_url": f"/h3_lvm/source_preview_proxy?ticket={token}",
        "proxy_recommended": str(info.get("codec_name") or "").lower()
        in PROXY_RECOMMENDED_CODECS,
        "expires_in": PREVIEW_TTL_SECONDS,
        "name": os.path.basename(path),
        "duration_sec": info.get("duration_sec"),
        "width": info.get("width"),
        "height": info.get("height"),
        "codec_name": info.get("codec_name"),
    }


def create_source_preview(video="", custom_path=""):
    """Authorize one selected path without exposing a general file-read endpoint."""
    return _create_path_preview(resolve_video_path(video, custom_path))


def create_upload_preview(project, segment_id):
    """Authorize one existing upload card without accepting a disk path."""
    path, record = resolve_upload(project, segment_id)
    data = _create_path_preview(path)
    data["name"] = record.get("original_name") or data["name"]
    data["segment_id"] = record.get("segment_id")
    return data


def _ticket_source(ticket):
    """Resolve only an unexpired ticket; a URL can never supply a disk path."""
    token = str(ticket or "")
    if not token or len(token) > 256:
        raise ValueError("预览票据无效，请重新打开原视频预览。")
    now = time.monotonic()
    with _lock:
        _purge(now)
        item = _tickets.get(token)
        if item is None:
            raise ValueError("预览已过期，请重新打开原视频预览。")
        path = item["path"]
    if not os.path.isfile(path):
        raise ValueError("原视频已不存在或无法读取。")
    return token, path


def _proxy_key(path):
    stat = os.stat(path)
    identity = "\0".join((
        str(PROXY_FORMAT_VERSION), os.path.normcase(os.path.realpath(path)),
        str(stat.st_size), str(stat.st_mtime_ns),
    ))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _proxy_file(path):
    root = os.path.join(folder_paths.get_temp_directory(), "h3-lvm-source-preview")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, _proxy_key(path) + ".mp4")


def _compatible_preview(path):
    """Build one bounded-size H.264 preview; never alter the selected source."""
    output = _proxy_file(path)
    if os.path.isfile(output) and os.path.getsize(output) > 0:
        return output
    key = os.path.basename(output)
    with _lock:
        lock = _proxy_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _proxy_locks[key] = lock
    with lock:
        if os.path.isfile(output) and os.path.getsize(output) > 0:
            return output
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("生成兼容预览需要 FFmpeg，请在 ComfyUI 环境中安装后重试。")
        temporary = output + f".{os.getpid()}.{threading.get_ident()}.tmp.mp4"
        scale = (f"scale='min(iw,{PROXY_MAX_SIDE})':'min(ih,{PROXY_MAX_SIDE})':"
                 "force_original_aspect_ratio=decrease:force_divisible_by=2")
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
            "-map", "0:v:0", "-map", "0:a:0?", "-vf", scale,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", temporary,
        ]
        try:
            result = subprocess.run(
                command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                errors="replace", check=False,
            )
            if result.returncode != 0 or not os.path.isfile(temporary) or os.path.getsize(temporary) == 0:
                detail = (result.stderr or result.stdout or "未知 FFmpeg 错误").strip()[-1200:]
                raise RuntimeError(f"生成 H.264 兼容预览失败：{detail}")
            os.replace(temporary, output)
        finally:
            if os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError:
                    pass
        return output


def create_compatible_source_preview(ticket):
    token, path = _ticket_source(ticket)
    _compatible_preview(path)
    return {
        "url": f"/h3_lvm/source_preview?ticket={token}&proxy=1",
        "name": os.path.basename(path),
        "proxy": True,
    }


def source_preview_path(ticket, proxy=False):
    """Resolve the source or an already-built proxy for one unexpired ticket."""
    _token, path = _ticket_source(ticket)
    if not proxy:
        return path
    output = _proxy_file(path)
    if not os.path.isfile(output) or os.path.getsize(output) == 0:
        raise ValueError("兼容预览尚未生成，请重新打开预览。")
    return output


def clear_source_previews():
    with _lock:
        _tickets.clear()


__all__ = [
    "PREVIEW_TTL_SECONDS", "PROXY_MAX_SIDE", "clear_source_previews",
    "create_compatible_source_preview", "create_source_preview", "create_upload_preview",
    "source_preview_path",
]
