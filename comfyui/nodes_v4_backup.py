"""ComfyUI H3 Long Video Manager — Node Registration (v3: +save bin).

v3 changes:
- Added project_name / save_enabled / save_preview_mp4 widgets
- Save-all loop: every segment is sliced once, saved to the H3 Segment Bin
- Live output remains the selected segment (backward compatible)
- Save failures are non-fatal (loud warning, node still produces output)
"""

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
    from core.h3_grid import is_valid_h3_frame_count, align_down_to_h3_grid
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

    def align_down_to_h3_grid(n):
        if n <= 5:
            return 5
        k = (n - 5) // 17
        return 17 * k + 5

# --- Segment store import (Phase A + B) ---
try:
    from .segment_store import (
        save_segment as _save_segment,
        load_segment,
        load_project_index,
        list_project,
        list_projects,
        sanitize_project_name,
        DEFAULT_PROJECT,
    )
    STORE_AVAILABLE = True
except ImportError:
    try:
        import segment_store
        _save_segment = segment_store.save_segment
        load_segment = segment_store.load_segment
        load_project_index = segment_store.load_project_index
        list_project = segment_store.list_project
        list_projects = segment_store.list_projects
        sanitize_project_name = segment_store.sanitize_project_name
        DEFAULT_PROJECT = segment_store.DEFAULT_PROJECT
        STORE_AVAILABLE = True
    except ImportError:
        STORE_AVAILABLE = False
        print("[H3 Long Video Manager] segment_store not available (save/pick disabled)")
        _save_segment = None
        DEFAULT_PROJECT = "H3_LVM"

        def load_segment(*a, **kw):
            raise RuntimeError("segment_store not available")

        def load_project_index(*a, **kw):
            return {"total_segments": 0, "segments": []}

        def list_projects():
            return []

        def sanitize_project_name(name):
            s = str(name).strip() if name else ""
            return s or DEFAULT_PROJECT


def _slice_and_scale(
    video: torch.Tensor,
    src_start: int,
    src_end: int,
    target_w: int | None = None,
    target_h: int | None = None,
) -> torch.Tensor:
    """Slice [src_start, src_end) and optionally scale. Returns [F,H,W,C] float [0,1]."""
    result = video[src_start:src_end].clone()
    if target_w is not None and target_h is not None:
        f, h, w, c = result.shape
        if target_w != w or target_h != h:
            flat = result.permute(0, 3, 1, 2).reshape(-1, c, h, w)
            flat = torch.nn.functional.interpolate(
                flat, size=(target_h, target_w), mode='bilinear', align_corners=False
            )
            result = flat.reshape(f, c, target_h, target_w).permute(0, 2, 3, 1)
    return result


def _slice_audio(
    audio,
    src_start_frame: int,
    src_end_frame: int,
    src_fps: float,
):
    """Slice audio to match [src_start_frame, src_end_frame) at src_fps.

    Handles: plain dict, VHS dict-like (_dict attr), or (waveform, sr) tuple.
    Returns ({"waveform": ..., "sample_rate": ...} or None, waveform or None, sample_rate)
    """
    if audio is None:
        return None, None, 44100

    # Normalize to dict
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
        return None, None, sample_rate

    time_start = src_start_frame / src_fps
    time_end = src_end_frame / src_fps
    audio_start = max(0, int(time_start * sample_rate))
    audio_end = min(int(time_end * sample_rate), waveform.shape[-1])
    audio_end = max(audio_start + 1, audio_end)

    sliced = {"waveform": waveform[:, :, audio_start:audio_end].clone(), "sample_rate": sample_rate}
    return sliced, waveform[:, :, audio_start:audio_end].clone(), sample_rate


def _make_silent_audio(duration_sec: float) -> dict:
    """Generate a silent audio dict for the given duration."""
    samples = max(1, int(duration_sec * 44100))
    return {"waveform": torch.zeros(1, 1, samples), "sample_rate": 44100}


class H3LongVideoManager:
    """H3 Long Video Manager — extract H3-compatible segments from video + audio.

    v3: saves all segments to the H3 Segment Bin, outputs selected segment live.

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
                "motion_context_frames": (["0", "5", "22", "39", "56"], {"default": "22"}),
                "segment_id": ("INT", {"default": 1, "min": 1, "max": 999}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "scale_percent": ("FLOAT", {"default": 100.0, "min": 10.0, "max": 100.0, "step": 1.0}),
                "align_to_h3_grid": ("BOOLEAN", {"default": True}),
                "project_name": ("STRING", {"default": DEFAULT_PROJECT, "placeholder": "留空 → 默认库：H3_LVM"}),
                "save_enabled": ("BOOLEAN", {"default": True}),
                "save_preview_mp4": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "INT", "INT")
    RETURN_NAMES = ("IMAGE", "AUDIO", "frame_count", "total_segments")
    FUNCTION = "process"
    CATEGORY = "H3/Video"

    def process(self, video, video_fps, segment_duration, motion_context_frames, segment_id,
                audio=None, scale_percent=100.0, align_to_h3_grid=True,
                project_name=DEFAULT_PROJECT, save_enabled=True, save_preview_mp4=False):
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
            print(f"  Seg {seg.segment_id + 1}: main=[{seg.main_start_frame},{seg.main_end_frame}) "
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

        # --- Working timeline → source timeline mapping ---
        working_fps = manifest.working_info.fps
        src_fps = float(video_fps)

        # Target resolution (after scale)
        target_w = manifest.working_info.width
        target_h = manifest.working_info.height
        need_scale = (scale_percent < 100.0) and (target_w != src_w or target_h != src_h)

        # --- Save all segments (Phase A) ---
        if save_enabled and STORE_AVAILABLE:
            project = project_name if project_name and str(project_name).strip() else DEFAULT_PROJECT
            print(f"[H3 LVM] saving {total_segments} segments to project '{project}'")
            for idx, seg in enumerate(manifest.segments):
                seg_id_1based = idx + 1
                src_start = min(int(round(seg.extraction_start_frame * src_fps / working_fps)), total_frames)
                src_end = min(int(round(seg.extraction_end_frame * src_fps / working_fps)), total_frames)
                src_start = max(0, src_start)
                src_end = max(src_start + 1, src_end)

                # Align to H3 grid
                actual_frames = src_end - src_start
                if align_to_h3_grid and not is_valid_h3_frame_count(actual_frames):
                    aligned = align_down_to_h3_grid(actual_frames)
                    if aligned < 5:
                        aligned = 5
                    src_end = src_start + aligned
                    actual_frames = aligned

                try:
                    # Slice video
                    seg_video = _slice_and_scale(video, src_start, src_end,
                                                 target_w if need_scale else None,
                                                 target_h if need_scale else None)

                    # Slice audio
                    seg_audio, seg_waveform, seg_sr = _slice_audio(audio, src_start, src_end, src_fps)
                    if seg_audio is None:
                        dur_sec = (src_end - src_start) / src_fps
                        seg_audio = _make_silent_audio(dur_sec)
                        seg_waveform = seg_audio["waveform"]
                        seg_sr = seg_audio["sample_rate"]

                    # Save
                    _save_segment(
                        project=project,
                        seg_index_1based=seg_id_1based,
                        video=seg_video,
                        audio=seg_audio,
                        fps=int(working_fps),
                        save_mp4=save_preview_mp4,
                        meta={
                            "main_start": seg.main_start_frame,
                            "main_end": seg.main_end_frame,
                            "main_frames": seg.main_frame_count,
                            "context_frames": seg.context_length,
                        },
                    )
                except Exception as e:
                    print(f"[H3 LVM] WARNING: failed to save segment {seg_id_1based}: {e}")
                    import traceback
                    traceback.print_exc()

            print(f"[H3 LVM] save complete: {total_segments} segments → '{project}'")
        elif save_enabled and not STORE_AVAILABLE:
            print("[H3 LVM] WARNING: segment_store not available, skipping save.")
        else:
            print("[H3 LVM] save disabled (pure live mode)")

        # --- Output selected segment (backward compatible) ---
        seg = manifest.get_segment(segment_id - 1)
        h3_valid = is_valid_h3_frame_count(seg.main_frame_count)

        print(f"[H3 LVM] selected segment {segment_id} (index {segment_id - 1}):")
        print(f"  main:     [{seg.main_start_frame}, {seg.main_end_frame}) = {seg.main_frame_count} frames {'(17n+5 ✓)' if h3_valid else ''}")
        print(f"  context:  [{seg.context_start_frame}, {seg.context_end_frame}) = {seg.context_length} frames")
        print(f"  extract:  [{seg.extraction_start_frame}, {seg.extraction_end_frame}) = {seg.extraction_frame_count} frames")

        src_start = min(int(round(seg.extraction_start_frame * src_fps / working_fps)), total_frames)
        src_end = min(int(round(seg.extraction_end_frame * src_fps / working_fps)), total_frames)
        src_start = max(0, src_start)
        src_end = max(src_start + 1, src_end)

        # Enforce H3 grid alignment on the actual output (safety net)
        actual_frames = src_end - src_start
        if align_to_h3_grid and not is_valid_h3_frame_count(actual_frames):
            aligned = align_down_to_h3_grid(actual_frames)
            if aligned < 5:
                aligned = 5
            src_end = src_start + aligned
            actual_frames = aligned
            print(f"  [aligned output to {aligned} frames (17n+5)]")

        # Slice video
        result_video = _slice_and_scale(video, src_start, src_end,
                                        target_w if need_scale else None,
                                        target_h if need_scale else None)

        final_frame_count = result_video.shape[0]
        print(f"[H3 LVM] output video: {final_frame_count} frames, {result_video.shape[2]}x{result_video.shape[1]}")

        # Slice audio
        result_audio, _, _ = _slice_audio(audio, src_start, src_end, src_fps)
        if result_audio is None:
            duration_sec = (src_end - src_start) / src_fps
            result_audio = _make_silent_audio(duration_sec)
            print(f"[H3 LVM] no audio input, outputting silent audio: {duration_sec:.3f}s")
        else:
            wf = result_audio["waveform"]
            duration_sec = wf.shape[-1] / result_audio["sample_rate"]
            print(f"[H3 LVM] output audio: {duration_sec:.3f}s, {wf.shape[-1]} samples @ {result_audio['sample_rate']}Hz")

        return (result_video, result_audio, final_frame_count, total_segments)


class H3SegmentPicker:
    """H3 Segment Picker — load a saved segment from the H3 Segment Bin.

    No video input needed. Reads the tensor bundle (safetensors) saved by
    the H3 Long Video Manager and outputs IMAGE + AUDIO directly.

    Feed the outputs into MiniMaxH3ReferenceToVideo ref_videos / ref_audio.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project_name": ("STRING", {"default": DEFAULT_PROJECT, "placeholder": "库名（默认 H3_LVM）"}),
                "segment_id": ("INT", {"default": 1, "min": 1, "max": 999}),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "INT")
    RETURN_NAMES = ("IMAGE", "AUDIO", "frame_count")
    FUNCTION = "process"
    CATEGORY = "H3/Video"

    def process(self, project_name, segment_id):
        if not STORE_AVAILABLE:
            raise RuntimeError("segment_store module not available. Cannot load saved segments.")

        project = project_name if project_name and str(project_name).strip() else DEFAULT_PROJECT
        project = sanitize_project_name(project)

        # Load index to validate
        idx = load_project_index(project)
        total = idx.get("total_segments", 0)

        if total == 0:
            # List available projects for helpful error
            projects = list_projects()
            raise ValueError(
                f"Project '{project}' has no saved segments. "
                f"Available projects: {projects if projects else '(none)'}\n"
                f"Run the H3 Long Video Manager node first to save segments."
            )

        if segment_id < 1 or segment_id > total:
            raise ValueError(
                f"segment_id={segment_id} out of range [1, {total}] for project '{project}'."
            )

        # Load
        video, audio, meta = load_segment(project, segment_id)

        frame_count = video.shape[0]
        print(f"[H3 LVM Picker] loaded segment {segment_id} from '{project}': "
              f"{frame_count} frames, {video.shape[2]}x{video.shape[1]}, "
              f"{'with audio' if audio else 'no audio'}")

        # Ensure audio is not None (H3 may require it)
        if audio is None:
            duration_sec = frame_count / meta.get("fps", 24)
            audio = {"waveform": torch.zeros(1, 1, max(1, int(duration_sec * 44100))), "sample_rate": 44100}
            print(f"[H3 LVM Picker] no audio saved, generating silent: {duration_sec:.2f}s")

        return (video, audio, frame_count)


NODE_CLASS_MAPPINGS = {
    "H3 Long Video Manager": H3LongVideoManager,
    "H3 Segment Picker": H3SegmentPicker,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3 Long Video Manager": "H3 Long Video Manager",
    "H3 Segment Picker": "H3 Segment Picker",
}

print("[H3 Long Video Manager] Plugin loaded (v3: +save bin +picker)")
