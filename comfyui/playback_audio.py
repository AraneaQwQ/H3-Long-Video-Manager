"""Pitch-preserving playback-speed audio processing shared by v1 and v2."""
from __future__ import annotations

import shutil
import subprocess

import numpy as np
import torch


def _atempo_filter(speed: float) -> str:
    """Build an atempo chain whose stages multiply to the requested speed."""
    stages = []
    factor = float(speed)
    while factor < 0.5:
        stages.append(0.5)
        factor /= 0.5
    stages.append(factor)
    return ",".join("atempo=%.6f" % stage for stage in stages)


def _slowdown_audio(audio, speed: float):
    """Time-stretch an AUDIO dict to the slowed timeline, keeping its pitch."""
    if audio is None:
        return None
    if isinstance(audio, dict):
        audio_data = audio
    elif hasattr(audio, "_dict"):
        audio_data = audio._dict
    else:
        waveform, sample_rate = audio[0], audio[1]
        audio_data = {"waveform": waveform, "sample_rate": sample_rate}
    waveform = audio_data.get("waveform")
    sample_rate = int(audio_data.get("sample_rate", 44100))
    if waveform is None:
        return audio
    samples = int(waveform.shape[-1])
    if samples == 0 or speed >= 1.0:
        return audio
    if waveform.ndim == 2:
        work = waveform.unsqueeze(0)
    elif waveform.ndim == 3:
        work = waveform
    else:
        print(f"[H3 playback] WARNING: audio waveform shape {list(waveform.shape)} "
              f"not understood; audio left at the original tempo.")
        return audio

    channels = int(work.shape[1])
    target_samples = max(1, int(round(samples / float(speed))))
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise ValueError(
            "H3 音频变速: 找不到 ffmpeg，无法做变速不变调（atempo）。"
            "请确认 ffmpeg 在 PATH 中；已拒绝用有损重采样代替。"
        )
    filter_chain = _atempo_filter(speed)
    command = [
        ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-f", "f32le", "-ar", str(sample_rate), "-ac", str(channels), "-i", "pipe:0",
        "-filter:a", filter_chain,
        "-f", "f32le", "-ar", str(sample_rate), "-ac", str(channels), "pipe:1",
    ]

    batches = []
    for batch in work.to(torch.float32).cpu():
        pcm = batch.transpose(0, 1).contiguous().numpy().astype("<f4", copy=False).tobytes()
        try:
            proc = subprocess.run(command, input=pcm, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=3600)
        except subprocess.TimeoutExpired:
            raise ValueError("H3 音频变速: atempo 处理超时，未产出结果。")
        if proc.returncode != 0 or not proc.stdout:
            tail = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-8:]
            raise ValueError("H3 音频变速: atempo 失败（退出码 %s）：%s"
                             % (proc.returncode, " | ".join(tail) or "ffmpeg 没有输出错误信息"))
        output = np.frombuffer(proc.stdout, dtype="<f4")
        if output.size % channels:
            raise ValueError("H3 音频变速: atempo 输出的 PCM 长度不是声道数的整数倍，"
                             "无法还原音频张量形状。")
        batches.append(torch.from_numpy(output.reshape(-1, channels).T.copy()))

    stretched = torch.stack(batches, dim=0)
    if stretched.shape[-1] > target_samples:
        stretched = stretched[..., :target_samples]
    elif stretched.shape[-1] < target_samples:
        stretched = torch.nn.functional.pad(
            stretched, (0, target_samples - stretched.shape[-1])
        )
    if waveform.ndim == 2:
        stretched = stretched.squeeze(0)
    print(f"[H3 playback] audio: atempo time-stretch {speed}x "
          f"({samples} -> {stretched.shape[-1]} samples @ {sample_rate} Hz, pitch kept)")
    return {"waveform": stretched.contiguous(), "sample_rate": sample_rate}


__all__ = ["_atempo_filter", "_slowdown_audio"]
