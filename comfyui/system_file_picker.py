"""Native Windows file dialog for a local ComfyUI host; returns a path, never bytes."""
from __future__ import annotations

import os
import platform
import threading

from .video_decode import probe_video
from .video_loader_node import resolve_video_path

_dialog_lock = threading.Lock()


def _windows_pick_file():
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilename(
            parent=root,
            title="选择 H3 源视频（只读取路径，不上传）",
            filetypes=[
                ("视频文件", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mts *.m2ts *.wmv"),
                ("所有文件", "*.*"),
            ],
        )
    finally:
        root.destroy()


def choose_system_video():
    """Open on the ComfyUI host, then validate the selected absolute path."""
    if platform.system() != "Windows":
        raise RuntimeError("系统文件选择框目前仅支持 Windows；请使用服务器文件浏览器或粘贴完整路径。")
    if not _dialog_lock.acquire(blocking=False):
        raise RuntimeError("系统文件选择框已经打开，请先完成或取消当前选择。")
    try:
        selected = _windows_pick_file()
        if not selected:
            return {"cancelled": True}
        path = os.path.realpath(resolve_video_path("", selected))
        info = probe_video(path)
        return {
            "cancelled": False,
            "path": path,
            "name": os.path.basename(path),
            "duration_sec": info.get("duration_sec"),
            "width": info.get("width"),
            "height": info.get("height"),
        }
    finally:
        _dialog_lock.release()


__all__ = ["choose_system_video"]
