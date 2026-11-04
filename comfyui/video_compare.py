"""Independent before/after video comparison node and its media routes."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
import uuid

import folder_paths
import torch
from comfy_api.latest import io

try:
    from aiohttp import web
except ImportError:
    web = None

from .segment_store import _decode_video
from .server_api import _csrf_block

logger = logging.getLogger(__name__)

NODE_ID = "H3 Video Compare Slider"
VHS_FILENAMES = io.Custom("VHS_FILENAMES")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
MAX_UPLOAD_BYTES = 8 * 1024 ** 3
MAX_RECORDING_BYTES = 512 * 1024 ** 2
RECORDING_TRANSCODE_TIMEOUT = 15 * 60
PREVIEW_MAX_FILES = 16
PREVIEW_MAX_AGE_SECONDS = 24 * 60 * 60


def _path_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in ("fullpath", "path", "video_path", "filename"):
            item = value.get(key)
            if isinstance(item, str):
                yield item
        for key in ("files", "filenames", "videos", "gifs"):
            yield from _path_values(value.get(key))
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _path_values(item)


def _find_video(value, label):
    roots = (
        "",
        folder_paths.get_output_directory(),
        folder_paths.get_temp_directory(),
        folder_paths.get_input_directory(),
    )
    for candidate in reversed(list(_path_values(value))):
        text = candidate.strip().strip('"')
        if os.path.splitext(text)[1].lower() not in VIDEO_EXTENSIONS:
            continue
        for root in roots:
            path = text if not root or os.path.isabs(text) else os.path.join(root, text)
            path = os.path.normpath(os.path.abspath(path))
            if os.path.isfile(path):
                return path
    raise ValueError(
        f"找不到{label}视频。请连接已生成视频的 Filenames 输出，或使用面板选择本地视频。"
    )


def _images_to_video(images, fps, label):
    if images is None:
        return None
    if getattr(images, "ndim", None) == 3:
        images = images.unsqueeze(0)
    if getattr(images, "ndim", None) != 4 or images.shape[0] < 1:
        raise ValueError(f"{label}图像输入必须是非空的 IMAGE 批次。")
    output_dir = folder_paths.get_temp_directory()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(
        output_dir, f"h3_compare_{label}_{uuid.uuid4().hex}.mp4"
    )
    if not _encode_images_mp4(images, float(fps), path):
        try:
            os.remove(path)
        except OSError:
            pass
        raise RuntimeError(
            f"无法把{label}IMAGE 批次编码为 MP4。请确认 FFmpeg 在 PATH 中，且输入帧形状正确。"
        )
    return path


def _ffmpeg_executable():
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _encode_images_mp4(images, fps, out_path):
    """Encode one frame at a time so a long IMAGE batch is never duplicated whole."""
    executable = _ffmpeg_executable()
    if not executable:
        logger.warning("[H3 Video Compare] FFmpeg not found; cannot create IMAGE preview.")
        return False
    frame_count, height, width, channels = images.shape
    if width % 2:
        width -= 1
    if height % 2:
        height -= 1
    if width < 2 or height < 2 or channels < 3:
        logger.warning("[H3 Video Compare] Unsupported IMAGE shape: %s", list(images.shape))
        return False
    command = [
        executable, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{width}x{height}", "-pix_fmt", "rgb24",
        "-r", str(fps), "-i", "-",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", out_path,
    ]
    process = None
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for index in range(frame_count):
            frame = _decode_video(images[index, :height, :width, :3])
            raw = (
                frame.detach().clamp(0, 1).mul(255).round()
                .to(torch.uint8)
                .contiguous().cpu().numpy().tobytes()
            )
            process.stdin.write(raw)
        process.stdin.close()
        returncode = process.wait(timeout=120)
        error = process.stderr.read().decode("utf-8", errors="replace").strip()
        if returncode != 0:
            logger.warning("[H3 Video Compare] IMAGE preview encode failed: %s", error[-800:])
            return False
        return os.path.isfile(out_path) and os.path.getsize(out_path) > 0
    except Exception as exc:
        logger.warning("[H3 Video Compare] IMAGE preview encode exception: %s", exc)
        if process is not None:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=10)
            except Exception:
                pass
        return False
    finally:
        if process is not None and process.stderr is not None:
            try:
                process.stderr.close()
            except OSError:
                pass


def _cleanup_compare_previews(keep=(), now=None):
    """Bound only this node's temporary previews; never touch unrelated temp files."""
    root = folder_paths.get_temp_directory()
    keep_paths = {os.path.normcase(os.path.realpath(path)) for path in keep if path}
    current_time = time.time() if now is None else float(now)
    candidates = []
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for entry in entries:
        if not entry.name.startswith("h3_compare_") or not entry.name.endswith(".mp4"):
            continue
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            path = os.path.realpath(entry.path)
            if os.path.normcase(path) in keep_paths:
                continue
            stat = entry.stat(follow_symlinks=False)
            candidates.append((stat.st_mtime, path))
        except OSError:
            continue
    candidates.sort(reverse=True)
    for index, (modified, path) in enumerate(candidates):
        if index < PREVIEW_MAX_FILES and current_time - modified <= PREVIEW_MAX_AGE_SECONDS:
            continue
        _remove_file(path)


def _inside_directory(path, directory):
    try:
        return os.path.commonpath((os.path.normcase(path), os.path.normcase(directory))) == os.path.normcase(directory)
    except ValueError:
        return False


def _readable_media(raw_path):
    path = os.path.realpath(os.path.normpath(os.path.abspath(str(raw_path or "").strip())))
    if os.path.splitext(path)[1].lower() not in VIDEO_EXTENSIONS:
        raise ValueError("不支持的视频格式。")
    allowed_roots = (
        os.path.realpath(os.path.normpath(os.path.abspath(folder_paths.get_input_directory()))),
        os.path.realpath(os.path.normpath(os.path.abspath(folder_paths.get_output_directory()))),
        os.path.realpath(os.path.normpath(os.path.abspath(folder_paths.get_temp_directory()))),
    )
    if not any(_inside_directory(path, root) for root in allowed_roots):
        raise PermissionError("只允许预览 ComfyUI 的 input、output 和 temp 目录内的视频。")
    if not os.path.isfile(path):
        raise FileNotFoundError("视频文件不存在。")
    return path


def _remove_file(path):
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


async def _write_part_limited(part, path, maximum, label):
    total = 0
    with open(path, "wb") as stream:
        while True:
            chunk = await part.read_chunk(size=1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise ValueError(f"{label}超过 {maximum // (1024 ** 2)} MiB 限制。")
            stream.write(chunk)
    if total < 1:
        raise ValueError(f"{label}是空文件。")
    return total


def _convert_recording(source, destination):
    executable = _ffmpeg_executable()
    if not executable:
        raise RuntimeError("保存 MP4 需要 FFmpeg。")
    command = [
        executable, "-y", "-loglevel", "error", "-i", source,
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", destination,
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False,
            timeout=RECORDING_TRANSCODE_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("录制视频转码超过 15 分钟，已停止。") from exc
    if (completed.returncode != 0 or not os.path.isfile(destination)
            or os.path.getsize(destination) < 1):
        raise RuntimeError(f"录制视频转码失败：{completed.stderr[-800:]}")


def register_video_compare_routes():
    if web is None:
        return
    try:
        from server import PromptServer
    except ImportError:
        return
    prompt_server = getattr(PromptServer, "instance", None)
    if prompt_server is None or not hasattr(prompt_server, "routes"):
        return
    if getattr(prompt_server, "_h3_video_compare_routes", False):
        return

    @prompt_server.routes.get("/h3_lvm/video_compare/media")
    async def compare_media(request):
        try:
            path = _readable_media(request.query.get("path"))
        except PermissionError as exc:
            return web.json_response({"error": str(exc)}, status=403)
        except (ValueError, FileNotFoundError) as exc:
            return web.json_response({"error": str(exc)}, status=404)
        return web.FileResponse(path, headers={"Cache-Control": "no-cache"})

    @prompt_server.routes.post("/h3_lvm/video_compare/upload")
    async def compare_upload(request):
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        saved_path = ""
        try:
            reader = await request.multipart()
            async for part in reader:
                if part.name != "video" or not part.filename:
                    continue
                original_name = os.path.basename(str(part.filename)).replace(" ", "_")
                extension = os.path.splitext(original_name)[1].lower()
                if extension not in VIDEO_EXTENSIONS:
                    raise ValueError("请选择 MP4、MOV、WebM、MKV、AVI 或 M4V 视频。")
                os.makedirs(folder_paths.get_input_directory(), exist_ok=True)
                saved_path = os.path.join(
                    folder_paths.get_input_directory(),
                    f"h3_compare_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{original_name}",
                )
                await _write_part_limited(part, saved_path, MAX_UPLOAD_BYTES, "视频")
                break
            if not saved_path:
                raise ValueError("没有收到视频文件。")
            return web.json_response({
                "ok": True,
                "path": saved_path,
                "name": os.path.basename(saved_path),
            })
        except Exception as exc:
            _remove_file(saved_path)
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    @prompt_server.routes.post("/h3_lvm/video_compare/recording")
    async def compare_recording(request):
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        upload_path = ""
        output_path = ""
        try:
            reader = await request.multipart()
            async for part in reader:
                if part.name != "file" or not part.filename:
                    continue
                upload_path = os.path.join(
                    folder_paths.get_temp_directory(),
                    f"h3_compare_recording_{uuid.uuid4().hex}.webm",
                )
                os.makedirs(folder_paths.get_temp_directory(), exist_ok=True)
                await _write_part_limited(part, upload_path, MAX_RECORDING_BYTES, "录制文件")
                break
            if not upload_path:
                raise ValueError("没有收到录制文件。")
            os.makedirs(folder_paths.get_output_directory(), exist_ok=True)
            output_path = os.path.join(
                folder_paths.get_output_directory(),
                f"H3_Video_Compare_{uuid.uuid4().hex[:10]}.mp4",
            )
            await asyncio.to_thread(_convert_recording, upload_path, output_path)
            return web.json_response({
                "ok": True,
                "path": output_path,
                "name": os.path.basename(output_path),
            })
        except Exception as exc:
            _remove_file(output_path)
            logger.warning("[H3 Video Compare] Recording save failed: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)
        finally:
            _remove_file(upload_path)

    prompt_server._h3_video_compare_routes = True
    logger.info("[H3 Video Compare] Registered independent media routes.")


class H3VideoCompareSlider(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id=NODE_ID,
            display_name="H3 视频对比滑块",
            category="H3/Video",
            description=(
                "并排同步播放两个视频，用可拖动的分割线比较处理前后效果。"
                "支持 IMAGE 批次、Video Helper Suite 的 Filenames，以及面板直接选择视频；"
                "也可以全屏缩放和录制对比画面。此节点由 H3LVM 独立实现，不依赖 VRGDG。"
            ),
            search_aliases=["video compare", "before after", "对比", "滑块", "VRGDG Video Compare Slider"],
            is_output_node=True,
            inputs=[
                io.Float.Input("slider_position", display_name="初始分割位置", default=0.5,
                               min=0.0, max=1.0, step=0.01),
                io.String.Input("before_label", display_name="左侧标签", default="原视频"),
                io.String.Input("after_label", display_name="右侧标签", default="处理后"),
                io.Boolean.Input("show_labels", display_name="显示标签", default=True),
                io.Boolean.Input("loop", display_name="循环播放", default=True),
                io.Boolean.Input("muted", display_name="静音", default=True,
                                 tooltip="关闭静音后播放原视频的声音。"),
                io.Float.Input("record_duration", display_name="录制时长（秒）", default=5.0,
                               min=0.5, max=300.0, step=0.5),
                io.Float.Input("fps", display_name="IMAGE 帧率", default=24.0,
                               min=1.0, max=240.0, step=0.1,
                               tooltip="只用于把 IMAGE 批次转成预览视频；文件输入保留自身帧率。"),
                io.Image.Input("before_images", display_name="原视频 IMAGE", optional=True),
                io.Image.Input("after_images", display_name="处理后 IMAGE", optional=True),
                VHS_FILENAMES.Input("before_video", display_name="原视频 Filenames", optional=True),
                VHS_FILENAMES.Input("after_video", display_name="处理后 Filenames", optional=True),
                io.String.Input("before_selected", default="", optional=True),
                io.String.Input("after_selected", default="", optional=True),
            ],
            outputs=[
                VHS_FILENAMES.Output(display_name="before_video"),
                VHS_FILENAMES.Output(display_name="after_video"),
            ],
        )

    @classmethod
    def execute(cls, slider_position, before_label, after_label, show_labels, loop,
                muted, record_duration, fps=24.0, before_images=None, after_images=None,
                before_video=None, after_video=None, before_selected="", after_selected=""):
        before_path = None
        after_path = None
        try:
            before_path = (
                _images_to_video(before_images, fps, "before")
                if before_images is not None
                else _find_video(before_selected or before_video, "原")
            )
            after_path = (
                _images_to_video(after_images, fps, "after")
                if after_images is not None
                else _find_video(after_selected or after_video, "处理后")
            )
        except Exception:
            if before_images is not None:
                _remove_file(before_path)
            if after_images is not None:
                _remove_file(after_path)
            raise
        generated = [
            path for path, images in ((before_path, before_images), (after_path, after_images))
            if images is not None
        ]
        if generated:
            _cleanup_compare_previews(keep=generated)
        return io.NodeOutput(
            (True, [before_path]),
            (True, [after_path]),
            ui={
                "h3_video_compare": [
                    {"role": "before", "path": before_path, "name": os.path.basename(before_path)},
                    {"role": "after", "path": after_path, "name": os.path.basename(after_path)},
                ],
                "h3_video_compare_settings": {
                    "slider_position": float(slider_position),
                    "before_label": str(before_label or "原视频"),
                    "after_label": str(after_label or "处理后"),
                    "show_labels": bool(show_labels),
                    "loop": bool(loop),
                    "muted": bool(muted),
                    "record_duration": max(0.5, float(record_duration)),
                    "fps": float(fps),
                },
            },
        )


__all__ = ["H3VideoCompareSlider", "register_video_compare_routes"]
