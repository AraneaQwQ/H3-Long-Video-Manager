"""Native Windows file dialog for a local ComfyUI host; returns a path, never bytes."""
from __future__ import annotations

import logging
import os
import platform
import threading

from .video_decode import probe_video
from .video_loader_node import resolve_video_path

logger = logging.getLogger(__name__)

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


def _explorer_windows():
    """Every visible Explorer folder window as (handle, title)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    windows = []

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        class_name = ctypes.create_unicode_buffer(64)
        if not user32.GetClassNameW(hwnd, class_name, 64) or class_name.value != "CabinetWClass":
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        windows.append((hwnd, title.value))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(visit), 0)
    return windows


def _raise_explorer(folder: str, previous, timeout: float = 2.0) -> bool:
    """Bring the Explorer window for ``folder`` above the windows already on screen.

    Windows refuses foreground to a window opened by a process that is not in front,
    which is exactly the ComfyUI server: the folder opens, but behind the browser. The
    window itself is fine, so this finds the one the shell just created (or reused) and
    raises it with the documented Alt-key foreground unlock.
    """
    import ctypes
    import time
    from ctypes import wintypes

    name = os.path.basename(folder.rstrip("\\/"))
    deadline = time.monotonic() + timeout
    while True:
        windows = _explorer_windows()
        fresh = [hwnd for hwnd, _ in windows if hwnd not in previous]
        if fresh:
            hwnd = fresh[-1]
            break
        if name:
            matched = [hwnd for hwnd, title in windows if name in title]
            if matched:
                hwnd = matched[-1]
                break
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)

    user32 = ctypes.windll.user32
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE: a minimised window has to come back first
    user32.BringWindowToTop(hwnd)
    if user32.SetForegroundWindow(hwnd):
        return True
    # A background process cannot normally take the foreground; a quick Alt press
    # releases that lock, which is the documented workaround for SetForegroundWindow.
    user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
    user32.keybd_event(0x12, 0, 0x0002, 0)  # VK_MENU up
    if user32.SetForegroundWindow(hwnd):
        return True
    # Last resort for a locked-down desktop: the call Alt+Tab itself uses.
    user32.SwitchToThisWindow(hwnd, True)
    return True


def open_local_folder(path: str) -> None:
    """Reveal one folder in the host's file manager; only the path is used."""
    if platform.system() != "Windows":
        raise RuntimeError("打开本地目录目前仅支持 Windows。")
    target = os.path.realpath(path)
    previous = set()
    try:
        previous = {hwnd for hwnd, _ in _explorer_windows()}
    except Exception:
        logger.warning("[H3 LVM] Could not list the open Explorer windows", exc_info=True)
    os.startfile(target)
    try:
        if not _raise_explorer(target, previous):
            logger.debug("[H3 LVM] Explorer window for %s was not found in time", target)
    except Exception:
        # The folder did open; only raising it failed, which the user can do by
        # clicking the taskbar entry. Never turn that into a failed API call.
        logger.warning("[H3 LVM] Could not bring the opened folder to the front", exc_info=True)


__all__ = ["choose_system_video", "open_local_folder"]
