"""ComfyUI H3 Clip Exporter — Extract & Save clips from video tensor.

H3ClipExporter: Takes a video tensor + project name, loads the cutter state,
extracts the specified clip (physical extraction range), saves to segment store
(synchronously), and outputs the clip's IMAGE + AUDIO.

Frame Rate Conversion:
- Cutter works in 24fps-equivalent frame space (MiniMax H3 target)
- Exporter receives source video tensor (e.g. 60fps)
- Converts 24fps frame range → source frame range for slicing
- Resamples (抽帧) the sliced result to exact 24fps frame count
- Audio is sliced by time (using 24fps time base)

Architecture:
- Synchronous execution (tensor is guaranteed alive during process())
- Loads alignment info from H3 Visual Cutter's saved state
- Saves MP4 + WAV + cover PNG to segment store (Picker-compatible)
- Peak memory: one clip at a time

Usage:
1. Run H3 Visual Cutter (path mode) → select cut points → state saved
2. Connect your video tensor → H3 Clip Exporter → outputs 24fps clip to H3 / MiniMax
"""

from __future__ import annotations

import sys
import os
import json
import time
import logging
import threading

logger = logging.getLogger(__name__)

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

import torch

try:
    from core.cutter_state import load_state, state_to_aligned, verify_source_identity
    from core.h3_grid import align_down_to_h3_grid
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False

try:
    from .segment_store import (
        save_segment as _save_segment,
        sanitize_project_name,
        DEFAULT_PROJECT,
    )
    STORE_AVAILABLE = True
except ImportError:
    try:
        import segment_store
        _save_segment = segment_store.save_segment
        sanitize_project_name = segment_store.sanitize_project_name
        DEFAULT_PROJECT = segment_store.DEFAULT_PROJECT
        STORE_AVAILABLE = True
    except ImportError:
        STORE_AVAILABLE = False

        def sanitize_project_name(name):
            import re
            s = str(name).strip() if name else "H3_LVM"
            return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", s)
        DEFAULT_PROJECT = "H3_LVM"


TARGET_FPS = 24  # MiniMax H3 requires 24fps output


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _resample_frames(video: torch.Tensor, target_count: int) -> torch.Tensor:
    """Resample video to exactly target_count frames by even sampling (抽帧).
    
    - If source has MORE frames than target: evenly sample target_count frames
    - If source has FEWER frames: pad by repeating last frame (should not happen
      with correct source_fps)
    - If equal: return as-is (no copy)
    """
    src_count = video.shape[0]
    if src_count == target_count:
        return video
    if src_count == 0:
        raise ValueError("Cannot resample empty video")
    
    if src_count > target_count:
        # Downsample: pick target_count evenly-spaced frame indices
        # linspace gives us indices [0, src_count-1] with target_count steps
        indices = torch.linspace(0, src_count - 1, target_count).long()
        return video[indices]
    else:
        # Upsample (source_fps < 24 case — normally rejected, but handle gracefully)
        # Use nearest-neighbor index mapping
        indices = torch.linspace(0, src_count - 1, target_count).long().clamp(0, src_count - 1)
        return video[indices]


def _slice_video(video: torch.Tensor, start: int, end: int,
                 target_w: int | None = None, target_h: int | None = None) -> torch.Tensor:
    """Slice [start, end) from video tensor with optional scaling."""
    start = max(0, start)
    end = min(video.shape[0], end)
    result = video[start:end]
    
    if target_w and target_h and result.shape[0] > 0:
        f, h, w, c = result.shape
        if target_w != w or target_h != h:
            flat = result.permute(0, 3, 1, 2).reshape(-1, c, h, w)
            flat = torch.nn.functional.interpolate(
                flat, size=(target_h, target_w), mode='bilinear', align_corners=False
            )
            result = flat.reshape(f, c, target_h, target_w).permute(0, 2, 3, 1)
            del flat
    return result


def _slice_audio(audio, time_start: float, time_end: float):
    """Slice audio by time range [time_start, time_end) in seconds.
    
    Returns (dict_or_None, sample_rate).
    """
    if audio is None:
        return None, 44100
    
    if isinstance(audio, dict):
        audio_data = audio
    elif hasattr(audio, '_dict'):
        audio_data = audio._dict
    else:
        waveform, sample_rate = audio[0], audio[1]
        audio_data = {"waveform": waveform, "sample_rate": sample_rate}
    
    waveform = audio_data.get("waveform")
    sample_rate = audio_data.get("sample_rate", 44100)
    
    if waveform is None:
        return None, sample_rate
    
    audio_start = max(0, int(time_start * sample_rate))
    audio_end = min(int(time_end * sample_rate), waveform.shape[-1])
    audio_end = max(audio_start + 1, audio_end)
    
    sliced = {"waveform": waveform[:, :, audio_start:audio_end].clone(), "sample_rate": sample_rate}
    return sliced, sample_rate


def _make_silent_audio(duration_sec: float) -> dict:
    samples = max(1, int(duration_sec * 44100))
    return {"waveform": torch.zeros(1, 1, samples), "sample_rate": 44100}


# ---------------------------------------------------------------------------
# Node definition
# ---------------------------------------------------------------------------

class H3ClipExporter:
    """H3 Clip Exporter — Extract a 24fps clip from video and save to segment store.
    
    Reads alignment info from H3 Visual Cutter's saved state.
    Handles frame-rate conversion: source fps → 24fps via frame extraction (抽帧).
    Synchronously extracts, saves (MP4+WAV+cover), and outputs the clip.
    
    Inputs:
        video: IMAGE tensor [F,H,W,C] float [0,1]
        audio: AUDIO (optional)
        fps: source video fps (must be >= 24)
        project_name: must match the Cutter's project name
        clip_id: which clip to export (1-based)
        scale_percent: optional downscale (100=original)
        save_to_bin: whether to save to segment store (for Picker)
    
    Outputs:
        IMAGE: the extracted 24fps clip [F,H,W,C] (17n+5 frames)
        AUDIO: the extracted clip audio (time-aligned)
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("IMAGE",),
                "fps": ("INT", {"default": 24, "min": 1, "max": 240,
                               "tooltip": "源视频帧率（VHS Load Video 的 fps）"}),
                "project_name": ("STRING", {
                    "default": "",
                    "placeholder": "项目名（必须与 Cutter 相同）"
                }),
                "clip_id": ("INT", {"default": 1, "min": 1, "max": 99, "placeholder": "片段编号"}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "scale_percent": ("FLOAT", {
                    "default": 100.0, "min": 10.0, "max": 100.0, "step": 1.0,
                    "placeholder": "缩小比例（100=原尺寸，对齐32倍数）"
                }),
                "save_to_bin": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "保存到 segment store（Picker 可读取）。关闭则只输出不存库。"
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("IMAGE", "AUDIO")
    FUNCTION = "process"
    CATEGORY = "H3/Video"
    DESCRIPTION = "Extract a 24fps clip from video tensor using H3 Cutter state. Handles frame-rate conversion (source fps → 24fps via 抽帧)."

    def process(self, video, fps, project_name, clip_id,
                audio=None, scale_percent=100.0, save_to_bin=True):
        if not CORE_AVAILABLE:
            raise RuntimeError("H3 core modules not available.")
        
        if not isinstance(video, torch.Tensor):
            raise TypeError(f"Expected IMAGE tensor [F,H,W,C], got {type(video).__name__}")
        
        fps = int(fps) if fps else 24
        if fps < TARGET_FPS:
            raise ValueError(
                f"源视频 fps={fps} 低于 {TARGET_FPS}。MiniMax H3 要求输入 fps ≥ 24。"
            )
        
        total_source_frames = video.shape[0]
        src_h, src_w = video.shape[1], video.shape[2]
        
        # --- Load cutter state ---
        project = sanitize_project_name(project_name.strip() if project_name else DEFAULT_PROJECT)
        state = load_state(project)
        if state is None:
            raise FileNotFoundError(
                f"No cutter state found for project '{project}'.\n"
                f"Run H3 Visual Cutter first with project_name='{project_name}'.\n"
                f"State directory: output/h3-lvm/cutter/{project}/"
            )
        
        # --- Read source_fps from state (primary source of truth) ---
        identity = state.get("source_identity", {})
        state_source_fps = int(identity.get("source_fps", fps))
        
        # Cross-check: state's source_fps should match user's fps parameter
        if state_source_fps != fps:
            print(f"[H3 Exporter] ⚠️  state.source_fps={state_source_fps} != input fps={fps}, "
                  f"using input fps={fps}")
            # Use user-provided fps (they know their video)
        
        # --- Get aligned clips ---
        aligned_clips = state_to_aligned(state)
        total_clips = len(aligned_clips)
        
        if clip_id < 1 or clip_id > total_clips:
            raise ValueError(
                f"clip_id={clip_id} out of range [1, {total_clips}].\n"
                f"Available clips: {total_clips}"
            )
        
        selected = aligned_clips[clip_id - 1]
        print(f"[H3 Exporter] project='{project}', clip {clip_id}/{total_clips}:")
        print(f"  manual:   [{selected.manual_start}, {selected.manual_end}) = {selected.manual_length}f (24fps)")
        print(f"  h3:       [{selected.h3_start}, {selected.h3_end}) = {selected.h3_length}f (17n+5 {'✓' if selected.h3_valid else '✗'})")
        print(f"  context:  [{selected.context_start}, {selected.context_end}) = {selected.context_length}f")
        print(f"  extract:  [{selected.extract_start}, {selected.extract_end}) = {selected.extract_length}f (24fps)")
        
        # --- Frame rate conversion: 24fps range → source frame range ---
        extract_start_24 = selected.extract_start
        extract_end_24 = selected.extract_end
        target_frame_count = extract_end_24 - extract_start_24  # This is 17n+5
        
        # Convert to source frame indices
        src_start = int(round(extract_start_24 * fps / TARGET_FPS))
        src_end = int(round(extract_end_24 * fps / TARGET_FPS))
        
        # Clamp to actual video bounds
        src_start = max(0, min(src_start, total_source_frames))
        src_end = max(src_start, min(src_end, total_source_frames))
        
        if fps != TARGET_FPS:
            print(f"[H3 Exporter] fps conversion: 24fps[{extract_start_24},{extract_end_24}) "
                  f"→ src[{src_start},{src_end}) = {src_end - src_start} frames @ {fps}fps")
        
        # --- Compute scale target ---
        if scale_percent < 100.0:
            target_w = max(32, int(src_w * scale_percent / 100.0) // 32 * 32)
            target_h = max(32, int(src_h * scale_percent / 100.0) // 32 * 32)
            print(f"[H3 Exporter] scale: {src_w}x{src_h} → {target_w}x{target_h} ({scale_percent}%, 32-aligned)")
        else:
            target_w = None
            target_h = None
        
        # --- Extract clip (SYNCHRONOUS — tensor is alive) ---
        out_video = _slice_video(video, src_start, src_end, target_w, target_h)
        
        # --- Resample to exact 24fps frame count (抽帧) ---
        actual_frames = out_video.shape[0]
        if actual_frames != target_frame_count:
            print(f"[H3 Exporter] resampling: {actual_frames}f → {target_frame_count}f (24fps)")
            out_video = _resample_frames(out_video, target_frame_count)
        else:
            print(f"[H3 Exporter] frame count matches: {actual_frames}f = {target_frame_count}f ✓")
        
        # --- Slice audio (by time, using 24fps time base) ---
        # The extract range is in 24fps frames, so time = frames / 24
        audio_time_start = extract_start_24 / TARGET_FPS
        audio_time_end = extract_end_24 / TARGET_FPS
        
        out_audio = None
        if audio is not None:
            out_audio, sr = _slice_audio(audio, audio_time_start, audio_time_end)
        if out_audio is None:
            out_duration = target_frame_count / TARGET_FPS
            out_audio = _make_silent_audio(out_duration)
            sr = out_audio["sample_rate"]
        
        out_frames = out_video.shape[0]
        out_duration = out_frames / TARGET_FPS
        print(f"[H3 Exporter] output: {out_frames} frames ({out_duration:.2f}s @ 24fps), "
              f"{out_video.shape[2]}x{out_video.shape[1]}, "
              f"audio={sr}Hz, {out_audio['waveform'].shape[-1]} samples")
        
        # --- Save to segment store (SYNCHRONOUS) ---
        if save_to_bin and STORE_AVAILABLE:
            try:
                _save_segment(
                    project=project,
                    seg_index_1based=clip_id,
                    video=out_video,
                    audio=out_audio,
                    fps=TARGET_FPS,  # Output is always 24fps
                    save_mp4=True,
                    meta={
                        "main_start": selected.manual_start,
                        "main_end": selected.manual_end,
                        "h3_start": selected.h3_start,
                        "h3_end": selected.h3_end,
                        "context_frames": selected.context_length,
                        "extract_start": extract_start_24,
                        "extract_end": extract_end_24,
                        "source_fps": fps,
                        "output_fps": TARGET_FPS,
                    },
                )
                print(f"[H3 Exporter] ✅ saved clip {clip_id} to project '{project}' (segment store, {TARGET_FPS}fps)")
            except Exception as e:
                print(f"[H3 Exporter] ⚠️  save failed: {e}")
                import traceback
                traceback.print_exc()
        
        return (out_video, out_audio)


NODE_CLASS_MAPPINGS = {
    "H3ClipExporter": H3ClipExporter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3ClipExporter": "H3 Clip Exporter",
}
