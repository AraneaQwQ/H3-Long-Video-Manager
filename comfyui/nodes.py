"""ComfyUI H3 Long Video Manager — Node Registration (v3: +save bin).

v3 changes:
- Added project_name / save_enabled / save_preview_mp4 widgets
- Save-all loop: every segment is sliced once, saved to the H3 Segment Bin
- Live output remains the selected segment (backward compatible)
- Save failures are reported as node errors; a completed run means all segments were saved.
"""

# Modified by RAFOLIE on 2026-09-28: native ComfyUI V3 schema and execution.
from comfy_api.latest import io

import logging
import torch

from ..core.models import MotionContextConfig, MOTION_CONTEXT_OPTIONS, SourceVideoInfo, WorkingVideoConfig
from ..core.manifest import build_manifest
from ..core.h3_grid import is_valid_h3_frame_count
from ..core.person_crop import crop_video_to_person
from ..core.smart_split import (
    assert_lossless, build_smart_segments, detect_scene_cuts,
)
from .segment_store import (
    save_segment as _save_segment, load_segment, load_project_index,
    list_project, list_projects, sanitize_project_name, DEFAULT_PROJECT,
    normalize_save_dtype,
)

logger = logging.getLogger(__name__)
CORE_AVAILABLE = True
STORE_AVAILABLE = True


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


def _pad_black_frames(video: torch.Tensor, target_frames: int) -> torch.Tensor:
    """Pad video tensor with black frames to reach target_frames.
    
    Args:
        video: [F, H, W, C] tensor
        target_frames: desired total frame count
    
    Returns:
        [target_frames, H, W, C] tensor with black padding appended
    """
    current = video.shape[0]
    if current >= target_frames:
        return video
    pad_count = target_frames - current
    h, w, c = video.shape[1], video.shape[2], video.shape[3]
    black = torch.zeros(pad_count, h, w, c, dtype=video.dtype, device=video.device)
    return torch.cat([video, black], dim=0)


def _pad_silent_audio(audio: dict, target_samples: int) -> dict:
    """Pad audio waveform with silence to reach target_samples."""
    wf = audio["waveform"]
    current = wf.shape[-1]
    if current >= target_samples:
        return audio
    pad_count = target_samples - current
    silence = torch.zeros(1, wf.shape[1], pad_count, dtype=wf.dtype, device=wf.device)
    padded_wf = torch.cat([wf, silence], dim=-1)
    return {"waveform": padded_wf, "sample_rate": audio["sample_rate"]}


def _resample_frames(video: torch.Tensor, target_frames: int) -> torch.Tensor:
    """Uniformly sample target_frames from video [F,H,W,C].
    
    Uses evenly-spaced index selection (no interpolation).
    Works for both downsample (60→24) and upsample (rare).
    """
    src_f = video.shape[0]
    if target_frames == src_f:
        return video
    if target_frames <= 1 or src_f <= 1:
        return video[:target_frames] if target_frames < src_f else video
    indices = torch.linspace(0, src_f - 1, target_frames).long()
    return video[indices].contiguous()


class H3LongVideoManager(io.ComfyNode):
    """H3 Long Video Manager — extract H3-compatible segments from video + audio.

    v3: saves all segments to the H3 Segment Bin, outputs selected segment live.

    Input:  IMAGE tensor [F,H,W,C] + AUDIO dict + source FPS
    Output: IMAGE tensor (selected segment) + AUDIO dict (matched) + INT frame_count + INT total_segments
    """

    @classmethod
    def fingerprint_inputs(cls, save_enabled=True, **kwargs):
        # Saving is a disk side effect: a cached output cannot recreate deleted assets.
        # Pure live processing retains the normal ComfyUI input cache.
        return float("nan") if save_enabled else False

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id='H3 Long Video Manager',
            display_name='H3 Long Video Manager',
            category='H3/Video',
            inputs=[
                io.Image.Input('video'),
                io.Int.Input('fps', default=24, min=1, max=240, tooltip='源视频帧率，用于时长和音频计算'),
                io.Float.Input('segment_duration', default=6.0, min=0.5, max=120.0, step=0.001,
                    tooltip='每段输出的固定时长（含 Motion Context 重叠帧）；实际帧数会向下取到 17n+5，例如 6.0s@24fps → 141 帧 = 5.875s'),
                io.Combo.Input('motion_context_frames', options=['0', '5', '22', '39', '56'], default='22'),
                io.Int.Input('segment_id', default=1, min=1, max=999),
                io.Audio.Input('audio', optional=True),
                io.Float.Input('scale_percent', optional=True, default=100.0, min=10.0, max=100.0, step=1.0),
                io.Boolean.Input('align_to_h3_grid', optional=True, default=True,
                    tooltip='关闭后不取 17n+5，每段正好等于所填时长（H3 可能会自行吸附帧数）'),
                io.String.Input('project_name', optional=True, default=DEFAULT_PROJECT, placeholder='留空 → 默认库：H3_LVM'),
                io.Boolean.Input('save_enabled', optional=True, default=True),
                io.Boolean.Input('save_preview_mp4', optional=True, default=False),
                # Kept only so old workflows still line up by position; the value
                # is ignored. The tail is decided automatically now.
                io.Combo.Input('final_align', options=['down', 'up'], optional=True, default='down',
                    tooltip='已废弃：末段现在自动处理（剩余帧会让最后一段变短，不重复、不补黑帧）'),
                io.Boolean.Input('person_crop', optional=True, default=False, tooltip='开启后检测人物并裁掉边缘，让人物占画面更大'),
                io.Int.Input('person_crop_expand_percent', optional=True, default=0, min=0, max=100, step=1, tooltip='人物框外扩百分比，0 为紧贴检测框（仍保持原画面比例）'),
                io.Combo.Input('save_dtype', options=['int8', 'fp16'], optional=True, default='int8',
                    tooltip='素材存盘精度：int8 体积只有 fp16 的一半（源视频本身是 8-bit，读回后画质一致）；fp16 是旧格式，需要保留原始浮点张量时再选'),
            ],
            outputs=[
                io.Image.Output(display_name='IMAGE'),
                io.Audio.Output(display_name='AUDIO'),
                io.Int.Output(display_name='frame_count'),
                io.Int.Output(display_name='total_segments'),
            ],
        )


    @classmethod
    def execute(cls, video, fps, segment_duration, motion_context_frames, segment_id,
                audio=None, scale_percent=100.0, align_to_h3_grid=True,
                project_name=DEFAULT_PROJECT, save_enabled=True, save_preview_mp4=False,
                final_align="down", person_crop=False, person_crop_expand_percent=0,
                save_dtype="int8"):
        # final_align is accepted but ignored: it only exists so graphs saved
        # before the automatic tail policy keep their widget positions.
        del final_align
        if not isinstance(video, torch.Tensor):
            raise TypeError(f"Expected IMAGE tensor [F,H,W,C], got {type(video).__name__}")

        fps = int(fps)
        expand_percent = max(0, min(100, int(person_crop_expand_percent)))
        work_video = video
        if person_crop:
            work_video, _crop_rect = crop_video_to_person(
                work_video, expand_percent=expand_percent
            )

        total_frames = work_video.shape[0]
        src_h, src_w = work_video.shape[1], work_video.shape[2]
        duration_sec = total_frames / fps
        print(f"[H3 LVM] input video: {total_frames} frames, {src_w}x{src_h}, fps={fps}, duration={duration_sec:.2f}s")
        if audio is not None:
            wf = audio.get("waveform") if isinstance(audio, dict) else None
            sr = audio.get("sample_rate", 44100) if isinstance(audio, dict) else 44100
            if wf is not None:
                print(f"[H3 LVM] input audio: waveform shape={list(wf.shape)}, sample_rate={sr}")

        # --- Build manifest ---
        source_info = SourceVideoInfo(
            file_path="input", width=src_w, height=src_h,
            fps=fps, frame_count=total_frames,
            duration_seconds=duration_sec,
        )

        working_config = WorkingVideoConfig(
            target_fps=fps,
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
        slice_frames = manifest.slice_frames or manifest.segment_duration_frames
        working_fps = manifest.working_info.fps
        slice_sec = slice_frames / working_fps
        print(f"[H3 LVM] === SEGMENT TABLE ({total_segments} segments, "
              f"{slice_frames}f = {slice_sec:.3f}s each) ===")
        for seg in manifest.segments:
            is_tail = seg.segment_id == total_segments - 1
            if is_valid_h3_frame_count(seg.extraction_frame_count):
                valid = '17n+5 ✓'
            elif is_tail:
                valid = 'not 17n+5 (tail, left to H3)'
            else:
                valid = 'not 17n+5'
            print(f"  Seg {seg.segment_id + 1}: extract=[{seg.extraction_start_frame},{seg.extraction_end_frame}) "
                  f"={seg.extraction_frame_count}f ({valid}), "
                  f"context={seg.context_length}f, main=[{seg.main_start_frame},{seg.main_end_frame}) "
                  f"={seg.main_frame_count}f")
        used = sum(seg.main_frame_count for seg in manifest.segments)
        source_total = manifest.working_info.total_frames
        tail = manifest.segments[-1] if total_segments else None
        unused = source_total - used
        tail_note = (
            f", tail {tail.extraction_frame_count}f (not aligned, left to H3)"
            if tail and tail.extraction_frame_count != slice_frames else ""
        )
        print(f"[H3 LVM] {used}/{source_total} source frames used"
              f"{'' if unused == 0 else f', {unused} unused'}{tail_note}")
        print(f"[H3 LVM] ==========================================")

        if segment_id < 1 or segment_id > total_segments:
            raise ValueError(
                f"segment_id={segment_id} out of range [1, {total_segments}]. "
                f"Source: {total_frames} frames @ {fps}fps → "
                f"{manifest.working_info.total_frames} frames @ {manifest.working_info.fps}fps → "
                f"{total_segments} segments of {manifest.slice_frames or manifest.segment_duration_frames} frames each"
            )

        # --- Timeline (1:1, no conversion) ---
        src_fps = float(fps)

        # Target resolution (after scale)
        target_w = manifest.working_info.width
        target_h = manifest.working_info.height
        need_scale = (scale_percent < 100.0) and (target_w != src_w or target_h != src_h)

        # --- Save all segments (Phase A) ---
        if save_enabled and STORE_AVAILABLE:
            project = project_name if project_name and str(project_name).strip() else DEFAULT_PROJECT
            print(f"[H3 LVM] saving {total_segments} segments to project '{project}'")
            saved_ids = []
            for idx, seg in enumerate(manifest.segments):
                seg_id_1based = idx + 1
                src_start = min(int(round(seg.extraction_start_frame * src_fps / working_fps)), total_frames)
                src_end = int(round(seg.extraction_end_frame * src_fps / working_fps))
                src_start = max(0, src_start)
                src_end = max(src_start + 1, src_end)
                # The manifest already fixed every segment length; re-aligning
                # here is what made segments drift between 6.6s and 7.3s.

                try:
                    # Slice video
                    seg_video = _slice_and_scale(work_video, src_start, src_end,
                                                 target_w if need_scale else None,
                                                 target_h if need_scale else None)
                    # Pad black frames if the slice came up short (fps rounding)
                    expected_f = src_end - src_start
                    if seg_video.shape[0] < expected_f:
                        seg_video = _pad_black_frames(seg_video, expected_f)

                    # Slice audio
                    seg_audio, seg_waveform, seg_sr = _slice_audio(audio, src_start, src_end, src_fps)
                    # Pad audio with silence if needed
                    if seg_audio is not None and seg_waveform is not None:
                        expected_samples = int(expected_f / src_fps * seg_sr)
                        if seg_waveform.shape[-1] < expected_samples:
                            seg_audio = _pad_silent_audio(seg_audio, expected_samples)
                            seg_waveform = seg_audio["waveform"]
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
                        save_dtype=save_dtype,
                        meta={
                            "main_start": seg.main_start_frame,
                            "main_end": seg.main_end_frame,
                            "main_frames": seg.main_frame_count,
                            "context_frames": seg.context_length,
                        },
                    )
                    saved_ids.append(seg_id_1based)
                except Exception as e:
                    raise RuntimeError(
                        f"H3 LVM: 保存项目 '{project}' 的片段 #{seg_id_1based} 失败。"
                        "请检查磁盘空间、写入权限或文件占用；本次保存未完成。"
                    ) from e

            print(f"[H3 LVM] save complete: {total_segments} segments → '{project}' "
                  f"(素材精度 {normalize_save_dtype(save_dtype)})")
            # Refresh other Picker nodes even if a downstream node later fails.
            import server
            prompt_server = getattr(server.PromptServer, "instance", None)
            if prompt_server is not None:
                # The ids let a Manager node show exactly what this run produced;
                # a plain project name would also force it to guess.
                prompt_server.send_sync("h3_lvm/changed", {
                    "project": project,
                    "segments": saved_ids,
                })
        elif save_enabled and not STORE_AVAILABLE:
            raise RuntimeError("H3 LVM: 素材存储模块不可用，无法保存片段。")
        else:
            print("[H3 LVM] save disabled (pure live mode)")

        # --- Output selected segment (backward compatible) ---
        seg = manifest.get_segment(segment_id - 1)
        h3_valid = is_valid_h3_frame_count(seg.extraction_frame_count)

        print(f"[H3 LVM] selected segment {segment_id} (index {segment_id - 1}):")
        print(f"  extract:  [{seg.extraction_start_frame}, {seg.extraction_end_frame}) = {seg.extraction_frame_count} frames {'(17n+5 ✓)' if h3_valid else ''}")
        print(f"  context:  [{seg.context_start_frame}, {seg.context_end_frame}) = {seg.context_length} frames")
        print(f"  main:     [{seg.main_start_frame}, {seg.main_end_frame}) = {seg.main_frame_count} frames")

        src_start = min(int(round(seg.extraction_start_frame * src_fps / working_fps)), total_frames)
        src_end = int(round(seg.extraction_end_frame * src_fps / working_fps))
        src_start = max(0, src_start)
        src_end = max(src_start + 1, src_end)
        # No re-alignment here either: the selected segment is already
        # slice_frames long (or the short tail at the end of the video).

        # Slice video
        result_video = _slice_and_scale(work_video, src_start, src_end,
                                        target_w if need_scale else None,
                                        target_h if need_scale else None)
        # Pad black frames if the slice came up short (fps rounding)
        expected_f = src_end - src_start
        if result_video.shape[0] < expected_f:
            result_video = _pad_black_frames(result_video, expected_f)

        final_frame_count = result_video.shape[0]
        print(f"[H3 LVM] output video: {final_frame_count} frames, {result_video.shape[2]}x{result_video.shape[1]}")

        # Slice audio
        result_audio, _, _ = _slice_audio(audio, src_start, src_end, src_fps)
        # Pad audio with silence if needed
        if result_audio is not None and result_audio.get("waveform") is not None:
            expected_samples = int(expected_f / src_fps * result_audio["sample_rate"])
            if result_audio["waveform"].shape[-1] < expected_samples:
                result_audio = _pad_silent_audio(result_audio, expected_samples)
        if result_audio is None:
            duration_sec = (src_end - src_start) / src_fps
            result_audio = _make_silent_audio(duration_sec)
            print(f"[H3 LVM] no audio input, outputting silent audio: {duration_sec:.3f}s")
        else:
            wf = result_audio["waveform"]
            duration_sec = wf.shape[-1] / result_audio["sample_rate"]
            print(f"[H3 LVM] output audio: {duration_sec:.3f}s, {wf.shape[-1]} samples @ {result_audio['sample_rate']}Hz")

        return io.NodeOutput(result_video, result_audio, final_frame_count, total_segments)


class H3SegmentPicker(io.ComfyNode):
    """H3 Segment Picker — load a saved segment from the H3 Segment Bin.

    No video input needed. Reads the tensor bundle (safetensors) saved by
    the H3 Long Video Manager and outputs IMAGE + AUDIO directly.

    Feed the outputs into MiniMaxH3ReferenceToVideo ref_videos / ref_audio.
    """

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id='H3 Segment Picker',
            display_name='H3 Segment Picker',
            category='H3/Video',
            inputs=[
                io.String.Input('project_name', default=DEFAULT_PROJECT, placeholder='库名（默认 H3_LVM）'),
                io.Int.Input('segment_id', default=1, min=1, max=999),
            ],
            outputs=[
                io.Image.Output(display_name='IMAGE'),
                io.Audio.Output(display_name='AUDIO'),
                io.Int.Output(display_name='frame_count'),
                io.Int.Output(display_name='segment_id'),
            ],
        )


    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        # The selected slot may be overwritten without changing widget values.
        return float("nan")

    @classmethod
    def execute(cls, project_name, segment_id):
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

        available = [s.get("segment_id") for s in idx.get("segments", [])]
        if segment_id not in available:
            raise ValueError(
                f"segment_id={segment_id} is not saved in project '{project}'. Available IDs: {available}"
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

        return io.NodeOutput(video, audio, frame_count, segment_id)


class H3SmartSplit(io.ComfyNode):
    """H3 Smart Split - cut the source video on real scene boundaries.

    Second producer for the SAME Project Segment Store:

        fixed  H3 Long Video Manager   17n+5 grid, equal slices
        smart  this node              real shot boundaries, no grid

    Detection runs once on the full input timeline, so a detected cut is a
    frame index of this very tensor. The four invariants are enforced by
    core.smart_split (no dropped frame / no duplicated main frame / no padding
    / no H3 alignment); extraction and storage are the Manager's own helpers,
    not a second copy. Output shape matches the Manager so the existing
    H3 Segment Picker reads either producer unchanged.
    """

    @classmethod
    def fingerprint_inputs(cls, save_enabled=True, **kwargs):
        # Saving is a disk side effect: a cached output cannot recreate deleted assets.
        return float("nan") if save_enabled else False

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id='H3 Smart Split',
            display_name='H3 Smart Split',
            category='H3/Video',
            inputs=[
                io.Image.Input('video'),
                io.Int.Input('fps', default=24, min=1, max=240, tooltip='源视频帧率，用于时长和音频计算'),
                io.Combo.Input('detection_sensitivity', options=['low', 'medium', 'high'], default='medium',
                    tooltip='镜头切点检测灵敏度：漏切选 high，误切过多选 low。只影响检测，不改变“不丢帧/不重复/不补帧”的切分结果'),
                io.Combo.Input('motion_context_frames', options=['0', '5', '22', '39', '56'], default='0',
                    tooltip='Motion Context 只增加当前镜头提取时的前置上下文，不改变镜头切点，也不进行 H3 17n+5 对齐'),
                io.Int.Input('segment_id', default=1, min=1, max=999),
                io.Audio.Input('audio', optional=True),
                io.Float.Input('scale_percent', optional=True, default=100.0, min=10.0, max=100.0, step=1.0),
                io.String.Input('project_name', optional=True, default=DEFAULT_PROJECT, placeholder='留空 → 默认库：H3_LVM'),
                io.Boolean.Input('save_enabled', optional=True, default=True),
                io.Boolean.Input('save_preview_mp4', optional=True, default=False),
                io.Combo.Input('save_dtype', options=['int8', 'fp16'], optional=True, default='int8',
                    tooltip='素材存盘精度：int8 体积只有 fp16 的一半（源视频本身是 8-bit，读回后画质一致）；fp16 是旧格式，需要保留原始浮点张量时再选'),
            ],
            outputs=[
                io.Image.Output(display_name='IMAGE'),
                io.Audio.Output(display_name='AUDIO'),
                io.Int.Output(display_name='frame_count'),
                io.Int.Output(display_name='total_segments'),
            ],
        )

    @classmethod
    def execute(cls, video, fps, detection_sensitivity, motion_context_frames, segment_id,
                audio=None, scale_percent=100.0, project_name=DEFAULT_PROJECT,
                save_enabled=True, save_preview_mp4=False, save_dtype="int8"):
        if not isinstance(video, torch.Tensor):
            raise TypeError(f"Expected IMAGE tensor [F,H,W,C], got {type(video).__name__}")
        if video.ndim != 4:
            raise ValueError(f"Expected IMAGE tensor [F,H,W,C], got shape {list(video.shape)}")

        fps = int(fps)
        total_frames = int(video.shape[0])
        src_h, src_w = int(video.shape[1]), int(video.shape[2])
        print(f"[H3 Smart Split] input video: {total_frames} frames, {src_w}x{src_h}, "
              f"fps={fps}, duration={total_frames / float(fps):.2f}s")
        if total_frames <= 0:
            raise ValueError("H3 Smart Split: 输入视频没有帧，无法检测镜头。")

        # --- 1. Detect on the FULL timeline, never on a pre-sliced one ---
        try:
            cuts, detect_meta = detect_scene_cuts(video, total_frames, fps, detection_sensitivity)
        except ImportError as exc:
            raise RuntimeError(str(exc)) from exc
        print(f"[H3 Smart Split] scene detection: {detect_meta['method']} "
              f"sensitivity={detect_meta['sensitivity']} threshold={detect_meta['adaptive_threshold']} "
              f"analysis={detect_meta['analysis_size']} -> {detect_meta['cut_count']} cuts "
              f"({detect_meta['scene_count']} scenes)")
        if cuts:
            print(f"[H3 Smart Split] cut frames: {cuts}")
        else:
            print("[H3 Smart Split] no scene cut found: the whole video is one segment "
                  "(a legal result, not an error).")

        # --- 2. Boundaries -> exact, contiguous segments (no grid, no padding) ---
        segments = build_smart_segments(total_frames, cuts, int(motion_context_frames))
        assert_lossless(segments, total_frames)
        total_segments = len(segments)

        print(f"[H3 Smart Split] === SEGMENT TABLE (SMART, {total_segments} segments) ===")
        for seg in segments:
            print(f"  Seg {seg['segment_id'] + 1} (scene {seg['scene_id'] + 1}): "
                  f"main=[{seg['main_start']},{seg['main_end']}) ={seg['main_frames']}f "
                  f"({seg['main_frames'] / float(fps):.3f}s), context={seg['context_frames']}f, "
                  f"extract=[{seg['extract_start']},{seg['extract_end']}) ={seg['extract_frames']}f")
        print(f"[H3 Smart Split] {sum(s['main_frames'] for s in segments)}/{total_frames} source "
              "frames covered: no dropped frame, no duplicated main frame, no padding, no 17n+5")
        print("[H3 Smart Split] ==========================================")

        if segment_id < 1 or segment_id > total_segments:
            raise ValueError(
                f"segment_id={segment_id} out of range [1, {total_segments}]. "
                f"Source: {total_frames} frames @ {fps}fps -> {total_segments} smart segments "
                f"(cuts at {cuts})"
            )

        # --- Resolution scaling: the Manager's own dimension math ---
        working = WorkingVideoConfig(
            target_fps=fps,
            scale_percent=scale_percent if scale_percent < 100.0 else None,
        )
        target_w, target_h = working.compute_working_dimensions(src_w, src_h)
        need_scale = (target_w != src_w or target_h != src_h)

        def _emit(seg):
            """Slice one smart segment with the Manager's extraction helpers."""
            start, end = int(seg["extract_start"]), int(seg["extract_end"])
            seg_video = _slice_and_scale(video, start, end,
                                        target_w if need_scale else None,
                                        target_h if need_scale else None)
            seg_audio, waveform, sr = _slice_audio(audio, start, end, float(fps))
            if seg_audio is not None and waveform is not None:
                expected_samples = int((end - start) / float(fps) * sr)
                if waveform.shape[-1] < expected_samples:
                    seg_audio = _pad_silent_audio(seg_audio, expected_samples)
            if seg_audio is None:
                seg_audio = _make_silent_audio((end - start) / float(fps))
            return seg_video, seg_audio

        # --- Save all segments into the existing Project Segment Store ---
        if save_enabled:
            if not STORE_AVAILABLE:
                raise RuntimeError("H3 Smart Split: 素材存储模块不可用，无法保存片段。")
            project = project_name if project_name and str(project_name).strip() else DEFAULT_PROJECT
            # The Store upserts by segment_id; it never clears the bin. Mixing a
            # Smart Split into a project that holds more (Fixed) segments leaves
            # the higher ids behind, so say so instead of pretending otherwise.
            stale = sorted(
                int(entry.get("segment_id", 0))
                for entry in load_project_index(project).get("segments", [])
                if int(entry.get("segment_id", 0)) > total_segments
            )
            if stale:
                print(f"[H3 Smart Split] WARNING: project '{project}' still keeps segment ids "
                      f"{stale}, which this Smart Split did not write. The store updates ids in "
                      "place and does not clear the bin; 需要清理请在素材库里删除这些片段。")
            print(f"[H3 Smart Split] saving {total_segments} segments to project '{project}'")
            saved_ids = []
            for seg in segments:
                seg_id_1based = int(seg["segment_id"]) + 1
                seg_video, seg_audio = _emit(seg)
                try:
                    _save_segment(
                        project=project,
                        seg_index_1based=seg_id_1based,
                        video=seg_video,
                        audio=seg_audio,
                        fps=fps,
                        save_mp4=save_preview_mp4,
                        save_dtype=save_dtype,
                        # Cover = first frame of the MAIN range, not of the
                        # Motion Context overlap the extraction starts with.
                        thumbnail_frame=int(seg["context_frames"]),
                        meta={
                            "main_start": seg["main_start"],
                            "main_end": seg["main_end"],
                            "main_frames": seg["main_frames"],
                            "context_frames": seg["context_frames"],
                            "segmentation_method": "smart",
                            "scene_id": seg["scene_id"],
                        },
                    )
                    saved_ids.append(seg_id_1based)
                except Exception as e:
                    raise RuntimeError(
                        f"H3 Smart Split: 保存项目 '{project}' 的片段 #{seg_id_1based} 失败。"
                        "请检查磁盘空间、写入权限或文件占用；本次保存未完成。"
                    ) from e
            print(f"[H3 Smart Split] save complete: {total_segments} segments -> '{project}' "
                  f"(素材精度 {normalize_save_dtype(save_dtype)})")
            import server
            prompt_server = getattr(server.PromptServer, "instance", None)
            if prompt_server is not None:
                prompt_server.send_sync("h3_lvm/changed", {
                    "project": project,
                    "segments": saved_ids,
                })
        else:
            print("[H3 Smart Split] save disabled (pure live mode)")

        # --- Output the selected segment (same contract as the Manager) ---
        seg = segments[int(segment_id) - 1]
        result_video, result_audio = _emit(seg)
        final_frame_count = int(result_video.shape[0])
        print(f"[H3 Smart Split] selected segment {segment_id} (scene {seg['scene_id'] + 1}): "
              f"extract=[{seg['extract_start']},{seg['extract_end']}) ={final_frame_count}f, "
              f"main=[{seg['main_start']},{seg['main_end']}) ={seg['main_frames']}f, "
              f"context={seg['context_frames']}f (not 17n+5: smart lengths are left to H3)")
        print(f"[H3 Smart Split] output video: {final_frame_count} frames, "
              f"{result_video.shape[2]}x{result_video.shape[1]}")
        return io.NodeOutput(result_video, result_audio, final_frame_count, total_segments)


NODE_LIST = [H3LongVideoManager, H3SmartSplit, H3SegmentPicker]



print("[H3 Long Video Manager] Plugin loaded (ComfyUI V3 API)")
