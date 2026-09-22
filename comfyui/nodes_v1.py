"""ComfyUI H3 Long Video Manager — Node Registration."""

import sys
import os
import logging

logger = logging.getLogger(__name__)

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

import torch

try:
    from core.models import (
        MotionContextConfig,
        MOTION_CONTEXT_OPTIONS,
        SourceVideoInfo,
        WorkingVideoConfig,
    )
    from core.manifest import build_manifest
    from core.h3_grid import is_valid_h3_frame_count
    CORE_AVAILABLE = True
    print("[H3 Long Video Manager] Core imported successfully")
except ImportError as e:
    CORE_AVAILABLE = False
    print(f"[H3 Long Video Manager] Core import FAILED: {e}")
    import traceback
    traceback.print_exc()

    class MotionContextConfig:
        def __init__(self, context_frames=22):
            self.context_frames = context_frames

    MOTION_CONTEXT_OPTIONS = (5, 22, 39, 56)
    SourceVideoInfo = None
    WorkingVideoConfig = None

    def build_manifest(*a, **kw):
        raise RuntimeError("Core module not available")

    def is_valid_h3_frame_count(n):
        return n >= 5 and (n - 5) % 17 == 0


class H3LongVideoManager:
    """H3 Long Video Manager — extract H3-compatible segments from video.

    Input:  IMAGE tensor [F,H,W,C] + source FPS
    Output: IMAGE tensor (aligned to 17n+5 frames) + INT frame_count
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("IMAGE",),
                "video_fps": ("INT", {"default": 24, "min": 1, "max": 240}),
                "segment_duration": ("FLOAT", {"default": 6.0, "min": 0.5, "max": 120.0, "step": 0.001}),
                "motion_context_frames": (["5", "22", "39", "56"], {"default": "22"}),
                "segment_id": ("INT", {"default": 0, "min": 0, "max": 999}),
            },
            "optional": {
                "scale_percent": ("FLOAT", {"default": 100.0, "min": 10.0, "max": 100.0, "step": 1.0}),
                "align_to_h3_grid": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "INT")
    RETURN_NAMES = ("IMAGE", "frame_count")
    FUNCTION = "process"
    CATEGORY = "H3/Video"

    def process(self, video, video_fps, segment_duration, motion_context_frames, segment_id,
                scale_percent=100.0, align_to_h3_grid=True):
        if not isinstance(video, torch.Tensor):
            raise TypeError(f"Expected IMAGE tensor [F,H,W,C], got {type(video).__name__}")

        total_frames = video.shape[0]
        src_h, src_w = video.shape[1], video.shape[2]
        print(f"[H3 LVM] input: {total_frames} frames, {src_w}x{src_h}, fps={video_fps}")

        source_info = SourceVideoInfo(
            file_path="input", width=src_w, height=src_h,
            fps=video_fps, frame_count=total_frames,
            duration_seconds=total_frames / video_fps,
        )

        working_config = WorkingVideoConfig(
            target_fps=24,
            scale_percent=scale_percent if scale_percent < 100.0 else None,
        )

        mc_config = MotionContextConfig(context_frames=int(motion_context_frames))
        manifest = build_manifest(
            source=source_info,
            working_config=working_config,
            segment_duration_seconds=segment_duration,
            motion_context=mc_config,
            align_to_h3=align_to_h3_grid,
        )

        if segment_id < 0 or segment_id >= len(manifest.segments):
            raise ValueError(
                f"segment_id={segment_id} out of range [0, {len(manifest.segments)-1}]. "
                f"Source: {total_frames} frames @ {video_fps}fps → "
                f"{manifest.working_info.total_frames} frames @ 24fps → "
                f"{len(manifest.segments)} segments of {manifest.segment_duration_frames} frames"
            )

        seg = manifest.get_segment(segment_id)
        out_frames = seg.extraction_end_frame - seg.extraction_start_frame
        h3_valid = is_valid_h3_frame_count(out_frames)

        print(f"[H3 LVM] segment {segment_id}:")
        print(f"  main:     [{seg.main_start_frame}, {seg.main_end_frame}) = {seg.main_frame_count} frames")
        print(f"  context:  [{seg.context_start_frame}, {seg.context_end_frame}) = {seg.context_length} frames")
        print(f"  extract:  [{seg.extraction_start_frame}, {seg.extraction_end_frame}) = {out_frames} frames")
        print(f"  H3 17n+5: {'VALID' if h3_valid else 'ALIGNED (was not on grid)'}")

        # Map working-timeline frame indices to source-timeline
        working_fps = manifest.working_info.fps
        src_fps = float(video_fps)

        src_start = min(int(round(seg.extraction_start_frame * src_fps / working_fps)), total_frames)
        src_end = min(int(round(seg.extraction_end_frame * src_fps / working_fps)), total_frames)
        src_start = max(0, src_start)
        src_end = max(src_start + 1, src_end)

        # Enforce H3 grid alignment on the actual output
        actual_frames = src_end - src_start
        if align_to_h3_grid and not is_valid_h3_frame_count(actual_frames):
            from core.h3_grid import align_down_to_h3_grid
            aligned = align_down_to_h3_grid(actual_frames)
            if aligned < 5:
                aligned = 5
            src_end = src_start + aligned
            actual_frames = aligned
            print(f"  [aligned output to {aligned} frames (17n+5)]")

        # Slice
        result = video[src_start:src_end].clone()

        # Scale if needed
        if scale_percent < 100.0:
            target_w = manifest.working_info.width
            target_h = manifest.working_info.height
            if target_w != src_w or target_h != src_h:
                f, h, w, c = result.shape
                flat = result.permute(0, 3, 1, 2).reshape(-1, c, h, w)
                flat = torch.nn.functional.interpolate(
                    flat, size=(target_h, target_w), mode='bilinear', align_corners=False
                )
                result = flat.reshape(f, c, target_h, target_w).permute(0, 2, 3, 1)

        final_count = result.shape[0]
        print(f"[H3 LVM] output: {final_count} frames, {result.shape[2]}x{result.shape[1]}")
        return (result, final_count)


NODE_CLASS_MAPPINGS = {
    "H3 Long Video Manager": H3LongVideoManager,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3 Long Video Manager": "H3 Long Video Manager",
}

print("[H3 Long Video Manager] Plugin loaded")
