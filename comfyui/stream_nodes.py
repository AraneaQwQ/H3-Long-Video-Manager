"""Independent v2 producers: file streaming, bounded memory, stable v1 untouched."""
from __future__ import annotations

import os

import torch
from comfy_api.latest import io

from ..core.h3_grid import fixed_slice_frames
from ..core.models import WorkingVideoConfig
from ..core.segmentation import compute_segment_duration_frames
from ..core.smart_split import (
    DEFAULT_SENSITIVITY,
    SENSITIVITY_THRESHOLDS,
    _post_process,
    _prepare_analysis_frames,
    _process_frame,
    _require_detector,
    _to_bgr_uint8,
    assert_lossless,
    build_smart_segments,
)
from ..core.stream_segments import iter_fixed_segment_batches, iter_smart_segment_batches
from .segment_store import DEFAULT_PROJECT, normalize_save_dtype, save_segment
from .stream_video import decode_audio_range, iter_video_frames, silent_audio, stack_uint8
from .video_decode import TARGET_FPS, probe_video
from .video_loader_node import list_input_videos, resolve_video_path


def _source_inputs():
    return [
        io.Combo.Input("video", options=list_input_videos() or [""],
                       tooltip="选择 input 内的视频，或使用下方完整路径；文件在执行时分批解码，不生成完整长视频 IMAGE。"),
        io.String.Input("custom_path", default="",
                        placeholder="可选：粘贴本地完整路径，优先于上方选单"),
    ]


def _outputs():
    return [
        io.Image.Output(display_name="IMAGE"),
        io.Audio.Output(display_name="AUDIO"),
        io.Int.Output(display_name="frame_count"),
        io.Int.Output(display_name="total_segments"),
    ]


def _target_size(info, scale_percent):
    working = WorkingVideoConfig(
        target_fps=TARGET_FPS,
        scale_percent=scale_percent if scale_percent < 100.0 else None,
    )
    return working.compute_working_dimensions(info["width"], info["height"])


def _notify(project, saved_ids):
    if not saved_ids:
        return
    import server
    prompt_server = getattr(server.PromptServer, "instance", None)
    if prompt_server is not None:
        prompt_server.send_sync("h3_lvm/changed", {
            "project": project, "segments": saved_ids,
        })


def _run_batches(
    path,
    batches,
    segment_id,
    project_name,
    save_enabled,
    save_preview_mp4,
    save_dtype,
    smart=False,
):
    project = project_name if str(project_name or "").strip() else DEFAULT_PROJECT
    selected = None
    saved_ids = []
    total = 0
    for meta, frames in batches:
        total += 1
        number = int(meta["segment_id"]) + 1
        video = stack_uint8(frames)
        audio = decode_audio_range(path, meta["extract_start"], meta["extract_frames"])
        if audio is None:
            audio = silent_audio(meta["extract_frames"])
        if save_enabled:
            extra = {
                "main_start": meta["main_start"],
                "main_end": meta["main_end"],
                "main_frames": meta["main_frames"],
                "context_frames": meta["context_frames"],
            }
            if smart:
                extra.update({"segmentation_method": "smart", "scene_id": meta["scene_id"]})
            try:
                save_segment(
                    project=project,
                    seg_index_1based=number,
                    video=video,
                    audio=audio,
                    fps=TARGET_FPS,
                    save_mp4=save_preview_mp4,
                    save_dtype=save_dtype,
                    thumbnail_frame=meta["context_frames"] if smart else 0,
                    meta=extra,
                )
                saved_ids.append(number)
            except Exception as exc:
                raise RuntimeError(
                    f"H3 v2：保存项目 '{project}' 的片段 #{number} 失败。"
                    "请检查磁盘空间、写入权限或文件占用；本次保存未完成。"
                ) from exc
        if number == segment_id:
            selected = (video, audio)
    if total == 0:
        raise ValueError("H3 v2：输入视频没有可解码的画面。")
    if selected is None:
        raise ValueError(f"segment_id={segment_id} 超出范围 [1, {total}]。")
    if save_enabled:
        _notify(project, saved_ids)
        print(f"[H3 v2] saved {total} streaming segments -> '{project}' "
              f"({normalize_save_dtype(save_dtype)})")
    video, audio = selected
    result = video.to(torch.float32).div(255.0)
    return io.NodeOutput(result, audio, int(result.shape[0]), total)


def _detect_file_cuts(path, sensitivity, estimated_total=0):
    """First Smart v2 pass: one small analysis frame at a time, never the full tensor."""
    AdaptiveDetector, FrameTimecode = _require_detector()
    key = str(sensitivity or DEFAULT_SENSITIVITY).strip().lower()
    if key not in SENSITIVITY_THRESHOLDS:
        key = DEFAULT_SENSITIVITY
    threshold = SENSITIVITY_THRESHOLDS[key]
    detector = AdaptiveDetector(adaptive_threshold=float(threshold))
    cuts = []
    total = 0
    analysis = "unknown"
    for frame in iter_video_frames(path):
        source = frame.to(torch.float32).div(255.0).unsqueeze(0)
        resized = _prepare_analysis_frames(source, 1)
        analysis = f"{int(resized.shape[2])}x{int(resized.shape[1])}"
        new_cuts = _process_frame(
            detector, FrameTimecode, total, _to_bgr_uint8(resized[0]),
            max(int(estimated_total), total + 1), TARGET_FPS)
        cuts.extend(int(cut.get_frames()) for cut in new_cuts)
        total += 1
    if total:
        cuts.extend(int(cut.get_frames()) for cut in _post_process(
            detector, FrameTimecode, total, TARGET_FPS))
    interior = sorted({cut for cut in cuts if 0 < cut < total})
    meta = {
        "method": "pyscenedetect_adaptive_stream",
        "detector": "AdaptiveDetector",
        "sensitivity": key,
        "adaptive_threshold": threshold,
        "min_scene_len": int(getattr(detector, "min_scene_len", 0) or 0),
        "analysis_size": analysis,
        "cut_count": len(interior),
        "scene_count": len(interior) + 1 if total else 0,
    }
    return total, interior, meta


class _V2Schema:
    @classmethod
    def validate_inputs(cls, video="", custom_path="", **kwargs):
        try:
            resolve_video_path(video, custom_path)
        except (OSError, ValueError) as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, save_enabled=True, **kwargs):
        if save_enabled:
            return float("nan")
        try:
            path = resolve_video_path(kwargs.get("video"), kwargs.get("custom_path"))
            stat = os.stat(path)
            return (path, stat.st_mtime_ns, stat.st_size, repr(sorted(kwargs.items())))
        except (OSError, ValueError):
            return repr(sorted(kwargs.items()))


class H3LongVideoManagerV2(_V2Schema, io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3 Long Video Manager v2",
            display_name="H3 Long Video Manager v2",
            category="H3/Video",
            description="文件流式定长裁切：直接读取磁盘视频，逐段保存，内存不随原视频总长增长；稳定版 v1 保持不变。",
            is_output_node=True,
            inputs=[
                *_source_inputs(),
                io.Float.Input("segment_duration", default=6.0, min=0.5, max=120.0, step=0.001),
                io.Combo.Input("motion_context_frames", options=["0", "5", "22", "39", "56"], default="22"),
                io.Int.Input("segment_id", default=1, min=1, max=999),
                io.Float.Input("scale_percent", optional=True, default=100.0, min=10.0, max=100.0, step=1.0),
                io.Boolean.Input("align_to_h3_grid", optional=True, default=True),
                io.String.Input("project_name", optional=True, default=DEFAULT_PROJECT),
                io.Boolean.Input("save_enabled", optional=True, default=True),
                io.Boolean.Input("save_preview_mp4", optional=True, default=False),
                io.Combo.Input("save_dtype", options=["int8", "fp16"], optional=True, default="int8"),
            ],
            outputs=_outputs(),
        )

    @classmethod
    def execute(cls, video, custom_path, segment_duration, motion_context_frames, segment_id,
                scale_percent=100.0, align_to_h3_grid=True, project_name=DEFAULT_PROJECT,
                save_enabled=True, save_preview_mp4=False, save_dtype="int8"):
        path = resolve_video_path(video, custom_path)
        info = probe_video(path)
        target_size = _target_size(info, scale_percent)
        slice_frames = fixed_slice_frames(
            compute_segment_duration_frames(segment_duration, TARGET_FPS), align_to_h3_grid)
        frames = iter_video_frames(path, target_size=target_size, source_info=info)
        batches = iter_fixed_segment_batches(frames, slice_frames, int(motion_context_frames))
        return _run_batches(path, batches, segment_id, project_name, save_enabled,
                            save_preview_mp4, save_dtype)


class H3SmartSplitV2(_V2Schema, io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3 Smart Split v2",
            display_name="H3 Smart Split v2",
            category="H3/Video",
            description="文件流式镜头裁切：第一遍低内存检测，第二遍逐镜头保存；不做 17n+5 对齐，稳定版 v1 保持不变。",
            is_output_node=True,
            inputs=[
                *_source_inputs(),
                io.Combo.Input("detection_sensitivity", options=["low", "medium", "high"], default="medium"),
                io.Combo.Input("motion_context_frames", options=["0", "5", "22", "39", "56"], default="0"),
                io.Int.Input("segment_id", default=1, min=1, max=999),
                io.Float.Input("scale_percent", optional=True, default=100.0, min=10.0, max=100.0, step=1.0),
                io.String.Input("project_name", optional=True, default=DEFAULT_PROJECT),
                io.Boolean.Input("save_enabled", optional=True, default=True),
                io.Boolean.Input("save_preview_mp4", optional=True, default=False),
                io.Combo.Input("save_dtype", options=["int8", "fp16"], optional=True, default="int8"),
            ],
            outputs=_outputs(),
        )

    @classmethod
    def execute(cls, video, custom_path, detection_sensitivity, motion_context_frames, segment_id,
                scale_percent=100.0, project_name=DEFAULT_PROJECT, save_enabled=True,
                save_preview_mp4=False, save_dtype="int8"):
        path = resolve_video_path(video, custom_path)
        info = probe_video(path)
        estimated_total = int(round((info.get("duration_sec") or 0) * TARGET_FPS))
        total, cuts, detect_meta = _detect_file_cuts(
            path, detection_sensitivity, estimated_total=estimated_total)
        if total <= 0:
            raise ValueError("H3 Smart Split v2：输入视频没有可解码的画面。")
        print(f"[H3 Smart Split v2] {detect_meta['method']}: {total} frames @24fps, cuts={cuts}")
        context = int(motion_context_frames)
        segments = build_smart_segments(total, cuts, context)
        assert_lossless(segments, total)
        target_size = _target_size(info, scale_percent)
        frames = iter_video_frames(path, target_size=target_size, source_info=info)
        batches = iter_smart_segment_batches(frames, segments, context)
        return _run_batches(path, batches, segment_id, project_name, save_enabled,
                            save_preview_mp4, save_dtype, smart=True)


NODE_LIST = [H3LongVideoManagerV2, H3SmartSplitV2]

__all__ = ["H3LongVideoManagerV2", "H3SmartSplitV2", "NODE_LIST"]
