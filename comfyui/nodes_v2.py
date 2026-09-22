"""ComfyUI H3 Long Video Manager — Node Registration (v2: +audio)."""

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
    """H3 Long Video Manager — extract H3-compatible segments from video + audio.

    Input:  IMAGE tensor [F,H,W,C] + AUDIO dict + source FPS
    Output: IMAGE tensor (selected segment) + AUDIO dict (matched) + INT frame_count + INT total_segments
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("IMAGE",),
                "video_fps": ("INT", {"default": 24, "min": 1, "max": 240}),
                "segment_duration": ("FLOAT", {"default": 6.0, "min": 0.5, "max": 120.0, "step": 0.001}),
                "motion_context_frames": (["5", "22", "39", "56"], {"default": "22"}),
                "segment_id": ("INT", {"default": 1, "min": 1, "max": 999}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "scale_percent": ("FLOAT", {"default": 100.0, "min": 10.0, "max": 100.0, "step": 1.0}),
                "align_to_h3_grid": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "INT", "INT")
    RETURN_NAMES = ("IMAGE", "AUDIO", "frame_count", "total_segments")
    FUNCTION = "process"
    CATEGORY = "H3/Video"

    def process(self, video, video_fps, segment_duration, motion_context_frames, segment_id,
                audio=None, scale_percent=100.0, align_to_h3_grid=True):
        if not isinstance(video, torch.Tensor):
            raise TypeError(f"Expected IMAGE tensor [F,H,W,C], got {type(video).__name__}")

        total_frames = video.shape[0]
        src_h, src_w = video.shape[1], video.shape[2]
        print(f"[H3 LVM] input video: {total_frames} frames, {src_w}x{src_h}, fps={video_fps}")
        if audio is not None:
            wf = audio.get("waveform") if isinstance(audio, dict) else None
            sr = audio.get("sample_rate", 44100) if isinstance(audio, dict) else 44100
            if wf is not None:
                print(f"[H3 LVM] input audio: waveform shape={list(wf.shape)}, sample_rate={sr}")

        # --- Build manifest ---
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

        total_segments = len(manifest.segments)

        # Print full segment table to console
        print(f"[H3 LVM] === SEGMENT TABLE ({total_segments} segments) ===")
        for seg in manifest.segments:
            valid = '17n+5 ✓' if is_valid_h3_frame_count(seg.main_frame_count) else 'not 17n+5'
            print(f"  Seg {seg.segment_id}: main=[{seg.main_start_frame},{seg.main_end_frame}) "
                  f"={seg.main_frame_count}f ({valid}), "
                  f"extract=[{seg.extraction_start_frame},{seg.extraction_end_frame}) "
                  f"={seg.extraction_frame_count}f")
        print(f"[H3 LVM] ==========================================")

        if segment_id < 1 or segment_id > total_segments:
            raise ValueError(
                f"segment_id={segment_id} out of range [1, {total_segments}]. "
                f"Source: {total_frames} frames @ {video_fps}fps → "
                f"{manifest.working_info.total_frames} frames @ 24fps → "
                f"{total_segments} segments of ~{manifest.segment_duration_frames} frames"
            )

        seg = manifest.get_segment(segment_id - 1)
        out_frames = seg.extraction_end_frame - seg.extraction_start_frame
        h3_valid = is_valid_h3_frame_count(seg.main_frame_count)

        print(f"[H3 LVM] selected segment {segment_id} (index {segment_id - 1}):")
        print(f"  main:     [{seg.main_start_frame}, {seg.main_end_frame}) = {seg.main_frame_count} frames {'(17n+5 ✓)' if h3_valid else ''}")
        print(f"  context:  [{seg.context_start_frame}, {seg.context_end_frame}) = {seg.context_length} frames")
        print(f"  extract:  [{seg.extraction_start_frame}, {seg.extraction_end_frame}) = {out_frames} frames")

        # --- Map working-timeline to source-timeline ---
        working_fps = manifest.working_info.fps
        src_fps = float(video_fps)

        src_start = min(int(round(seg.extraction_start_frame * src_fps / working_fps)), total_frames)
        src_end = min(int(round(seg.extraction_end_frame * src_fps / working_fps)), total_frames)
        src_start = max(0, src_start)
        src_end = max(src_start + 1, src_end)

        # Enforce H3 grid alignment on the actual output (safety net)
        actual_frames = src_end - src_start
        if align_to_h3_grid and not is_valid_h3_frame_count(actual_frames):
            from core.h3_grid import align_down_to_h3_grid
            aligned = align_down_to_h3_grid(actual_frames)
            if aligned < 5:
                aligned = 5
            src_end = src_start + aligned
            actual_frames = aligned
            print(f"  [aligned output to {aligned} frames (17n+5)]")

        # --- Slice video ---
        result_video = video[src_start:src_end].clone()

        # Scale if needed
        if scale_percent < 100.0:
            target_w = manifest.working_info.width
            target_h = manifest.working_info.height
            if target_w != src_w or target_h != src_h:
                f, h, w, c = result_video.shape
                flat = result_video.permute(0, 3, 1, 2).reshape(-1, c, h, w)
                flat = torch.nn.functional.interpolate(
                    flat, size=(target_h, target_w), mode='bilinear', align_corners=False
                )
                result_video = flat.reshape(f, c, target_h, target_w).permute(0, 2, 3, 1)

        final_frame_count = result_video.shape[0]
        print(f"[H3 LVM] output video: {final_frame_count} frames, {result_video.shape[2]}x{result_video.shape[1]}")

        # --- Slice audio ---
        result_audio = None
        if audio is not None:
            # Handle: plain dict, VHS dict-like object (_dict attr), or tuple
            if isinstance(audio, dict):
                audio_data = audio
            elif hasattr(audio, '_dict'):
                audio_data = audio._dict
            else:
                # Fallback: assume (waveform, sample_rate) tuple
                waveform, sample_rate = audio[0], audio[1]
                audio_data = {"waveform": waveform, "sample_rate": sample_rate}
            waveform = audio_data.get("waveform")
            sample_rate = audio_data.get("sample_rate", 44100)

            if waveform is not None:
                # Time range in seconds
                time_start = src_start / src_fps
                time_end = src_end / src_fps

                # Convert to sample indices
                audio_start = int(time_start * sample_rate)
                audio_end = int(time_end * sample_rate)

                # Clamp
                total_samples = waveform.shape[-1]
                audio_start = max(0, audio_start)
                audio_end = min(audio_end, total_samples)
                audio_end = max(audio_start + 1, audio_end)

                # Slice
                result_audio = {
                    "waveform": waveform[:, :, audio_start:audio_end].clone(),
                    "sample_rate": sample_rate,
                }
                duration_sec = (audio_end - audio_start) / sample_rate
                print(f"[H3 LVM] output audio: {duration_sec:.3f}s, {audio_end - audio_start} samples @ {sample_rate}Hz")
            else:
                result_audio = audio
        else:
            # No audio input — return silent audio matching video duration
            duration_sec = (src_end - src_start) / src_fps
            samples = max(1, int(duration_sec * 44100))
            silent = torch.zeros(1, 1, samples)
            result_audio = {"waveform": silent, "sample_rate": 44100}
            print(f"[H3 LVM] no audio input, outputting silent audio: {duration_sec:.3f}s")

        return (result_video, result_audio, final_frame_count, total_segments)


NODE_CLASS_MAPPINGS = {
    "H3 Long Video Manager": H3LongVideoManager,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3 Long Video Manager": "H3 Long Video Manager",
}

print("[H3 Long Video Manager] Plugin loaded (v2: +audio)")
