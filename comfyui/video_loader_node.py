"""Disk-first video loader for large H3 sources.

The combo deliberately has no upload control: selecting an existing file never
uploads it through the browser or ComfyUI's upload-size limit. PyAV reads the
server-side path at execution time and decodes directly to the H3 24 fps timeline.
"""
from __future__ import annotations

import os

import torch
from comfy_api.latest import io

import folder_paths

from .video_decode import (
    CUSTOM_MAX_SIDE_DEFAULT,
    DEFAULT_RESIZE,
    MAX_MAX_SIDE,
    MIN_MAX_SIDE,
    RESIZE_CUSTOM,
    RESIZE_OPTIONS,
    TARGET_FPS,
    decode_video,
    parse_max_side,
    probe_video,
)


def _input_root() -> str:
    return os.path.realpath(folder_paths.get_input_directory())


def _resolve_input_relative(relative="") -> str:
    """Resolve one browser/API path and prove it stays below input."""
    text = _clean_path(relative).replace("/", os.sep)
    if os.path.isabs(text):
        raise ValueError("文件浏览器只允许 input 文件夹内的相对路径。")
    root = _input_root()
    path = os.path.realpath(os.path.join(root, text))
    try:
        inside = os.path.commonpath([root, path]) == root
    except ValueError:
        inside = False
    if not inside:
        raise ValueError("文件浏览器路径不能离开 input 文件夹。")
    return path


def _is_video_name(name: str) -> bool:
    return bool(folder_paths.filter_files_content_types([name], ["video"]))


def list_input_videos() -> list[str]:
    """Videos below ComfyUI's input folder, including nested folders."""
    root = folder_paths.get_input_directory()
    found = []
    for current, directories, filenames in os.walk(root):
        directories.sort(key=str.casefold)
        for filename in sorted(filenames, key=str.casefold):
            relative = os.path.relpath(os.path.join(current, filename), root)
            if _is_video_name(relative):
                found.append(relative.replace(os.sep, "/"))
    return sorted(found, key=str.casefold)


def list_video_directory(directory="") -> dict:
    """One directory for the server-side file browser; never reads file bytes."""
    path = _resolve_input_relative(directory)
    if not os.path.isdir(path):
        raise ValueError(f"目录不存在：{path}")
    root = _input_root()
    current = os.path.relpath(path, root).replace(os.sep, "/")
    if current == ".":
        current = ""
    directories = []
    files = []
    for entry in os.scandir(path):
        relative = os.path.relpath(entry.path, root).replace(os.sep, "/")
        if entry.is_dir(follow_symlinks=True):
            directories.append({"name": entry.name, "path": relative})
        elif entry.is_file(follow_symlinks=True) and _is_video_name(entry.name):
            stat = entry.stat(follow_symlinks=True)
            files.append({
                "name": entry.name, "path": relative,
                "size_bytes": int(stat.st_size),
                "modified_ns": int(stat.st_mtime_ns),
            })
    directories.sort(key=lambda item: item["name"].casefold())
    files.sort(key=lambda item: item["name"].casefold())
    return {
        "directory": current,
        "parent": current.rpartition("/")[0] if current else None,
        "directories": directories,
        "files": files,
    }


def video_file_info(path="") -> dict:
    """Probe one selected input video; the API cannot probe arbitrary disk paths."""
    resolved = _resolve_input_relative(path)
    if not os.path.isfile(resolved) or not _is_video_name(resolved):
        raise ValueError(f"视频文件不存在：{path}")
    info = probe_video(resolved)
    relative = os.path.relpath(resolved, _input_root()).replace(os.sep, "/")
    info.update({"path": relative, "size_bytes": int(os.path.getsize(resolved))})
    return info


def _clean_path(value) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1].strip()
    return os.path.expanduser(os.path.expandvars(text))


def resolve_video_path(video="", custom_path="") -> str:
    """Resolve a combo entry below input, or an explicit local absolute path."""
    explicit = _clean_path(custom_path)
    selected = explicit or _clean_path(video)
    if not selected:
        raise ValueError(
            "H3 视频加载器：没有可读取的视频。请把视频复制到 ComfyUI 的 input "
            "文件夹后刷新节点列表，或在「本地完整路径」中粘贴视频路径。"
        )
    if os.path.isabs(selected):
        path = os.path.normpath(selected)
    else:
        root = os.path.abspath(folder_paths.get_input_directory())
        path = os.path.abspath(os.path.join(root, selected))
        if not explicit and os.path.commonpath([root, path]) != root:
            raise ValueError("H3 视频加载器：选单文件必须位于 input 文件夹内。")
    if not os.path.isfile(path):
        raise ValueError(f"H3 视频加载器：视频文件不存在或不可读取：{path}")
    return path


class H3VideoLoader(io.ComfyNode):
    """Read a server-side video without a browser upload; emit 24 fps IMAGE/AUDIO."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="H3 Video Loader",
            display_name="H3 视频加载器（24fps）",
            search_aliases=["large video", "load video", "大视频", "视频加载"],
            category="H3/Video",
            description=(
                "直接读取 ComfyUI 服务器磁盘上的视频，不经过浏览器上传，因此不受原生 "
                "Load Video 的上传大小限制。解码时按时间戳转为 24fps，并可先缩小画面再"
                "生成 IMAGE，适合作为 Manager / Smart Split 的输入。"
            ),
            inputs=[
                io.Combo.Input(
                    "video", options=list_input_videos() or [""],
                    tooltip="选择 ComfyUI input 文件夹内的视频（含子文件夹）。这里不上传文件；新复制的视频可刷新节点列表后出现。",
                ),
                io.String.Input(
                    "custom_path", default="",
                    placeholder="可选：粘贴本地完整路径，优先于上方选单",
                    tooltip="可选。粘贴运行 ComfyUI 的电脑可读取的视频完整路径；填写后忽略上方选单。不会复制或改写原文件。",
                ),
                io.Combo.Input(
                    "output_size", options=list(RESIZE_OPTIONS), default=DEFAULT_RESIZE,
                    tooltip="解码时等比限制最长边，先缩小再累积帧，降低内存压力；磁盘原文件不变。4K/2K 素材建议 1920 或 1280。",
                ),
                io.Int.Input(
                    "custom_max_side", default=CUSTOM_MAX_SIDE_DEFAULT,
                    min=MIN_MAX_SIDE, max=MAX_MAX_SIDE, step=2,
                    tooltip=f"仅在输出分辨率选择「{RESIZE_CUSTOM}」时生效。等比缩小、对齐偶数、不放大。",
                ),
            ],
            outputs=[
                io.Image.Output(display_name="IMAGE"),
                io.Audio.Output(display_name="AUDIO"),
                io.Int.Output(display_name="frame_count"),
                io.Int.Output(display_name="fps"),
            ],
        )

    @classmethod
    def validate_inputs(cls, video="", custom_path="", output_size=DEFAULT_RESIZE,
                        custom_max_side=CUSTOM_MAX_SIDE_DEFAULT):
        try:
            resolve_video_path(video, custom_path)
            parse_max_side(output_size, custom_max_side)
        except (OSError, ValueError) as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, video="", custom_path="", output_size=DEFAULT_RESIZE,
                           custom_max_side=CUSTOM_MAX_SIDE_DEFAULT):
        try:
            path = resolve_video_path(video, custom_path)
            stat = os.stat(path)
            return (
                path, stat.st_mtime_ns, stat.st_size, TARGET_FPS,
                parse_max_side(output_size, custom_max_side),
            )
        except (OSError, ValueError):
            return repr((video, custom_path, output_size, custom_max_side))

    @classmethod
    def execute(cls, video="", custom_path="", output_size=DEFAULT_RESIZE,
                custom_max_side=CUSTOM_MAX_SIDE_DEFAULT) -> io.NodeOutput:
        path = resolve_video_path(video, custom_path)
        max_side = parse_max_side(output_size, custom_max_side)
        image, audio, info = decode_video(path, target_fps=TARGET_FPS, max_side=max_side)
        frame_count = int(image.shape[0])
        if audio is None:
            samples = max(1, int(round(frame_count / float(TARGET_FPS) * 44100)))
            audio = {
                "waveform": torch.zeros(1, 1, samples, dtype=torch.float32),
                "sample_rate": 44100,
            }
        print(
            f"[H3 Video Loader] {path}: {info.get('source_fps') or 'unknown'}fps -> "
            f"{TARGET_FPS}fps, {frame_count} frames, "
            f"{image.shape[2]}x{image.shape[1]}, "
            f"{'with audio' if info.get('has_audio') else 'silent audio'}"
        )
        return io.NodeOutput(image, audio, frame_count, TARGET_FPS)


__all__ = [
    "H3VideoLoader", "list_input_videos", "list_video_directory",
    "resolve_video_path", "video_file_info",
]
