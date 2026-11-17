"""声学属性：能量 VAD、静音/停顿、语速、基频（librosa pyin）。

- 帧长 30 ms，帧 RMS 低于 P20 分位视为静音；有效语速 = 转写字符数 / 有效语音时长；
- 停顿 = 连续静音 ≥ 0.1 s 的片段；基频用 pyin（60–400 Hz），只统计有声帧；
- 口音无模型，标 ``unavailable``。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def _percentile(values: np.ndarray, percentile: float) -> float:
    return float(np.percentile(values, percentile)) if values.size else 0.0


def analyze(path: Path, cfg: dict[str, Any], transcript_chars: int) -> dict[str, Any]:
    import soundfile

    samples, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    mono = samples.mean(axis=1) if samples.ndim > 1 else samples
    frame = max(1, int(rate * float(cfg["vad"]["frameSec"])))
    frames = len(mono) // frame
    if frames == 0:
        return {
            "durationSec": round(len(mono) / rate, 6),
            "speechRatio": 0.0,
            "silenceRatio": 1.0,
            "speechSec": 0.0,
            "pauses": 0,
            "pauseSec": 0.0,
            "speechRateCharsPerSec": None,
            "pitchMeanHz": None,
            "pitchMedianHz": None,
            "voicedRatio": None,
            "accent": {"status": "unavailable", "reasonCode": "ACCENT_MODEL_UNAVAILABLE"},
        }
    energies = np.array(
        [float(np.sqrt(np.mean(mono[index * frame : (index + 1) * frame] ** 2))) for index in range(frames)]
    )
    threshold = _percentile(energies, float(cfg["vad"]["energyPercentile"]))
    speech = energies > threshold
    speech_sec = float(speech.sum()) * float(cfg["vad"]["frameSec"])
    silence = ~speech
    pauses = 0
    pause_frames = 0
    run = 0
    for flag in silence:
        if flag:
            run += 1
        else:
            if run * float(cfg["vad"]["frameSec"]) >= 0.1:
                pauses += 1
                pause_frames += run
            run = 0
    if run * float(cfg["vad"]["frameSec"]) >= 0.1:
        pauses += 1
        pause_frames += run

    pitch_stats = _pitch(mono, rate, cfg)
    return {
        "durationSec": round(len(mono) / rate, 6),
        "speechRatio": round(speech_sec / (frames * float(cfg["vad"]["frameSec"])), 6),
        "silenceRatio": round(1 - speech_sec / (frames * float(cfg["vad"]["frameSec"])), 6),
        "speechSec": round(speech_sec, 6),
        "pauses": pauses,
        "pauseSec": round(pause_frames * float(cfg["vad"]["frameSec"]), 6),
        "speechRateCharsPerSec": (
            round(transcript_chars / speech_sec, 6) if speech_sec > 0 else None
        ),
        "pitchMeanHz": pitch_stats["mean"],
        "pitchMedianHz": pitch_stats["median"],
        "voicedRatio": pitch_stats["voicedRatio"],
        "accent": {"status": "unavailable", "reasonCode": "ACCENT_MODEL_UNAVAILABLE"},
    }


def _pitch(mono: np.ndarray, rate: int, cfg: dict[str, Any]) -> dict[str, Any]:
    import librosa

    try:
        values = librosa.pyin(
            mono,
            fmin=float(cfg["quality"]["pitchMinHz"]),
            fmax=float(cfg["quality"]["pitchMaxHz"]),
            sr=rate,
        )[0]
    except Exception:  # noqa: BLE001 - 短音频/静音可能失败
        return {"mean": None, "median": None, "voicedRatio": None}
    voiced = values[~np.isnan(values)]
    if voiced.size == 0:
        return {"mean": None, "median": None, "voicedRatio": 0.0}
    return {
        "mean": round(float(np.mean(voiced)), 6),
        "median": round(float(np.median(voiced)), 6),
        "voicedRatio": round(float(voiced.size / values.size), 6),
    }
