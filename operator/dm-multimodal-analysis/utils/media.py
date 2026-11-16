"""图像/音频/视频解析：格式属性、EXIF、VAD、关键帧与音轨拆流。

依赖：Pillow（图像头/EXIF）、soundfile（WAV/FLAC 元数据）、ffmpeg（探测/解码/抽帧）。
所有属性来自实际解码或 ffmpeg 输出，不使用常量或随机值。
"""

from __future__ import annotations

import math
import mimetypes
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_RE = re.compile(r"Stream #\d+:\d+.*?: Video: ([^,]+),.*?(\d{2,5})x(\d{2,5})(?:.*?([\d.]+)\s*fps)?")
_AUDIO_RE = re.compile(
    r"Stream #\d+:\d+.*?: Audio: ([^,]+), (\d+) Hz, ([^,]+)(?:, ([^,]+))?(?:, (\d+) kb/s)?"
)
_BITRATE_RE = re.compile(r"bitrate:\s*(\d+) kb/s")
_PTS_RE = re.compile(r"pts_time:(?P<pts>[0-9.]+)")


class DependencyUnavailable(RuntimeError):
    """ffmpeg/解码器不可用。"""


class NoAudioStream(ValueError):
    """文件不含音频流。"""


_FFMPEG: str | None = None


def ffmpeg_exe() -> str:
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    candidate = shutil.which("ffmpeg")
    if not candidate:
        try:
            import imageio_ffmpeg  # type: ignore

            candidate = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001 - 依赖不可用统一转明确错误
            candidate = None
    if not candidate:
        raise DependencyUnavailable("ffmpeg 不可用")
    _FFMPEG = candidate
    return candidate


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, timeout=timeout, check=False,
    )


def probe_streams(path: Path, timeout: int = 60) -> dict[str, Any]:
    """解析 ``ffmpeg -i`` 的流信息（ffprobe 未安装时的等价实现）。"""

    result = _run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)], timeout=timeout,
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    info: dict[str, Any] = {"raw": _tail(stderr)}
    duration_match = _DURATION_RE.search(stderr)
    if duration_match:
        hours, minutes, seconds = duration_match.groups()
        info["durationSec"] = round(
            int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3
        )
    bitrate_match = _BITRATE_RE.search(stderr)
    if bitrate_match:
        info["bitrateKbps"] = int(bitrate_match.group(1))

    video_match = _VIDEO_RE.search(stderr)
    if video_match:
        codec, width, height, fps = video_match.groups()
        info["video"] = {
            "codec": codec.strip(),
            "width": int(width),
            "height": int(height),
            "fps": float(fps) if fps else None,
        }
    audio_match = _AUDIO_RE.search(stderr)
    if audio_match:
        codec, sample_rate, layout, sample_format, kbps = audio_match.groups()
        info["audio"] = {
            "codec": codec.strip(),
            "sampleRate": int(sample_rate),
            "layout": layout.strip(),
            "sampleFormat": (sample_format or "").strip() or None,
            "bitrateKbps": int(kbps) if kbps else None,
        }
    return info


def image_info(path: Path) -> dict[str, Any]:
    """Pillow header/EXIF/ICC 与真实解码校验。"""

    from PIL import Image

    result: dict[str, Any] = {
        "format": None,
        "mime": mimetypes.guess_type(path.name)[0],
        "decodable": False,
        "decodeError": None,
        "width": None,
        "height": None,
        "mode": None,
        "dpi": None,
        "hasIcc": False,
        "exif": {},
        "capturedAt": None,
    }
    try:
        with Image.open(path) as image:
            result.update(
                {
                    "format": image.format,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                    "dpi": _dpi(image.info.get("dpi")),
                    "hasIcc": bool(image.info.get("icc_profile")),
                }
            )
            result["exif"] = _exif_summary(image)
            if result["exif"].get("dateTimeOriginal"):
                result["capturedAt"] = result["exif"]["dateTimeOriginal"]
            image.load()
            result["decodable"] = True
    except Exception as exc:  # noqa: BLE001 - 解码失败是业务结果
        result["decodeError"] = f"{type(exc).__name__}: {exc}"
    return result


def audio_info(
    path: Path,
    cfg: dict[str, Any],
    *,
    work_dir: Path | None = None,
    stem: str | None = None,
    decode: bool = True,
) -> dict[str, Any]:
    """音频属性与 VAD；可选导出 16 kHz mono WAV。"""

    limits = cfg["limits"]
    audio_cfg = cfg["audio"]
    timeout = int(limits["ffmpegTimeoutSec"])
    result: dict[str, Any] = {
        "durationSec": None,
        "sampleRate": None,
        "channels": None,
        "codec": None,
        "bitrateKbps": None,
        "vad": None,
        "wavPath": None,
        "decodeError": None,
        "truncatedDecode": False,
    }
    probe = probe_streams(path, timeout=timeout)
    result["durationSec"] = probe.get("durationSec")
    if "audio" not in probe:
        raise NoAudioStream("文件不含音频流")
    stream = probe["audio"]
    result.update(
        {
            "codec": stream["codec"],
            "sampleRate": stream["sampleRate"],
            "channels": 2 if "stereo" in stream["layout"] else 1,
            "bitrateKbps": stream.get("bitrateKbps") or probe.get("bitrateKbps"),
        }
    )

    target_rate = int(audio_cfg["targetSampleRate"])
    wav_path = None
    if decode and work_dir is not None:
        wav_path = work_dir / f"{stem or path.stem}.wav"
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg_exe(), "-y", "-v", "error", "-i", str(path),
            "-vn", "-ac", str(int(audio_cfg["channels"])), "-ar", str(target_rate),
            "-c:a", "pcm_s16le",
            "-t", str(int(limits["maxAudioDecodeSec"])),
            str(wav_path),
        ]
        completed = _run(command, timeout=timeout)
        if completed.returncode != 0:
            result["decodeError"] = completed.stderr.decode("utf-8", errors="replace")[-800:]
            wav_path = None
        else:
            result["wavPath"] = wav_path
            if result["durationSec"] and result["durationSec"] > int(limits["maxAudioDecodeSec"]):
                result["truncatedDecode"] = True

    vad = _stream_vad(path, target_rate, audio_cfg, int(limits["maxAudioDecodeSec"]), timeout)
    if vad is not None:
        result["vad"] = vad
        if result["durationSec"] is None:
            result["durationSec"] = round(vad["frames"] * int(audio_cfg["vadFrameMs"]) / 1000, 3)
    return result


def video_info(
    path: Path,
    cfg: dict[str, Any],
    *,
    work_dir: Path,
    record_id: str,
) -> dict[str, Any]:
    """视频属性、关键帧与音轨拆流。"""

    limits = cfg["limits"]
    timeout = int(limits["ffmpegTimeoutSec"])
    probe = probe_streams(path, timeout=timeout)
    if "video" not in probe:
        raise ValueError("文件不含视频流")
    video = probe["video"]
    duration = probe.get("durationSec")
    fps = video.get("fps")
    frame_count = int(round(duration * fps)) if duration and fps else None
    result: dict[str, Any] = {
        "durationSec": duration,
        "width": video["width"],
        "height": video["height"],
        "fps": fps,
        "frameCount": frame_count,
        "frameCountSource": "duration*fps" if frame_count else None,
        "codec": video["codec"],
        "bitrateKbps": probe.get("bitrateKbps"),
        "hasAudio": "audio" in probe,
        "audio": probe.get("audio"),
        "keyframes": [],
        "keyframeError": None,
        "audioWavPath": None,
        "audioError": None,
    }

    if cfg["video"]["extractKeyframes"] and duration:
        max_frames = max(1, int(limits["maxKeyframes"]))
        step = max(1, int(math.floor((frame_count or max_frames) / max_frames)))
        frames_dir = work_dir / "keyframes" / record_id
        frames_dir.mkdir(parents=True, exist_ok=True)
        for stale in frames_dir.glob("*.jpg"):
            stale.unlink()
        pattern = frames_dir / "frame_%04d.jpg"
        command = [
            ffmpeg_exe(), "-y", "-v", "info", "-i", str(path),
            "-vf", f"select=not(mod(n\\,{step})),showinfo",
            "-fps_mode", "vfr", "-q:v", str(int(cfg["video"]["keyframeImageQuality"])),
            str(pattern),
        ]
        completed = _run(command, timeout=timeout)
        stderr = completed.stderr.decode("utf-8", errors="replace")
        timestamps = [float(item) for item in _PTS_RE.findall(stderr)]
        files = sorted(frames_dir.glob("frame_*.jpg"))
        for index, frame_path in enumerate(files):
            timestamp = timestamps[index] if index < len(timestamps) else None
            result["keyframes"].append(
                {
                    "index": index,
                    "tsSec": round(timestamp, 3) if timestamp is not None else None,
                    "path": frame_path,
                }
            )
        if not files:
            result["keyframeError"] = stderr[-800:]

    if cfg["video"]["extractAudioStream"] and result["hasAudio"]:
        wav_path = work_dir / "audio_streams" / f"{record_id}.wav"
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg_exe(), "-y", "-v", "error", "-i", str(path),
            "-vn", "-ac", str(int(cfg["audio"]["channels"])),
            "-ar", str(int(cfg["audio"]["targetSampleRate"])),
            "-c:a", "pcm_s16le",
            "-t", str(int(limits["maxAudioDecodeSec"])),
            str(wav_path),
        ]
        completed = _run(command, timeout=timeout)
        if completed.returncode == 0:
            result["audioWavPath"] = wav_path
        else:
            result["audioError"] = completed.stderr.decode("utf-8", errors="replace")[-800:]
    return result


def _stream_vad(
    path: Path, sample_rate: int, cfg: dict[str, Any], max_seconds: int, timeout: int,
) -> dict[str, Any] | None:
    """流式解码 16 kHz mono PCM 并逐帧计算能量，避免整段音频进内存。"""

    import threading

    command = [
        ffmpeg_exe(), "-v", "error", "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-t", str(max_seconds), "-",
    ]
    frame_samples = max(1, int(sample_rate * int(cfg["vadFrameMs"]) / 1000))
    frame_bytes = frame_samples * 2
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    killer = threading.Timer(timeout, process.kill)
    killer.start()
    energies: list[float] = []
    buffer = b""
    try:
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(1024 * 1024)
            if not chunk:
                break
            buffer += chunk
            usable = len(buffer) - (len(buffer) % frame_bytes)
            if usable:
                block = np.frombuffer(buffer[:usable], dtype="<i2").astype(np.float64) / 32768.0
                frames = block.reshape(-1, frame_samples)
                energies.extend(np.sqrt(np.mean(frames**2, axis=1)).tolist())
                buffer = buffer[usable:]
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    finally:
        killer.cancel()
    if not energies:
        return None
    rms = np.asarray(energies, dtype=np.float64)
    floor = float(cfg["vadEnergyFloor"])
    quantile = float(np.quantile(rms, float(cfg["vadQuantile"])))
    threshold = max(floor, quantile)
    speech = int(np.count_nonzero(rms > threshold))
    total = int(rms.size)
    return {
        "frames": total,
        "speechRatio": round(speech / total, 6),
        "silenceRatio": round((total - speech) / total, 6),
        "threshold": round(threshold, 8),
        "rmsMean": round(float(np.mean(rms)), 8),
        "rmsP95": round(float(np.quantile(rms, 0.95)), 8),
    }


def _vad(pcm: bytes, sample_rate: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """字节输入版 VAD（单测用）。"""

    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64) / 32768.0
    frame = max(1, int(sample_rate * int(cfg["vadFrameMs"]) / 1000))
    usable = len(samples) - (len(samples) % frame)
    if usable <= 0:
        return {"frames": 0, "speechRatio": 0.0, "silenceRatio": 1.0, "threshold": None}
    frames = samples[:usable].reshape(-1, frame)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    floor = float(cfg["vadEnergyFloor"])
    quantile = float(np.quantile(rms, float(cfg["vadQuantile"])))
    threshold = max(floor, quantile)
    speech = int(np.count_nonzero(rms > threshold))
    total = int(rms.size)
    return {
        "frames": total,
        "speechRatio": round(speech / total, 6),
        "silenceRatio": round((total - speech) / total, 6),
        "threshold": round(threshold, 8),
        "rmsMean": round(float(np.mean(rms)), 8),
        "rmsP95": round(float(np.quantile(rms, 0.95)), 8),
    }


def _exif_summary(image: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    try:
        exif = image.getexif()
    except Exception:  # noqa: BLE001 - 无 EXIF 不是错误
        return summary
    tags = {271: "make", 272: "model", 274: "orientation", 305: "software", 306: "dateTime"}
    for tag, name in tags.items():
        value = exif.get(tag)
        if value not in (None, ""):
            summary[name] = str(value)
    try:
        nested = exif.get_ifd(0x8769)
    except Exception:  # noqa: BLE001
        nested = {}
    if nested:
        if nested.get(36867):
            summary["dateTimeOriginal"] = _exif_datetime(str(nested[36867]))
        if nested.get(33434):
            summary["exposureTime"] = str(nested[33434])
        if nested.get(33437):
            summary["fNumber"] = str(nested[33437])
        if nested.get(34855):
            summary["iso"] = str(nested[34855])
    if "dateTimeOriginal" not in summary and summary.get("dateTime"):
        summary["dateTimeOriginal"] = _exif_datetime(summary["dateTime"])
    return summary


def _exif_datetime(raw: str) -> str | None:
    from datetime import datetime

    try:
        return datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S").isoformat(timespec="seconds")
    except ValueError:
        return None


def _dpi(raw: Any) -> list[float] | None:
    if not raw:
        return None
    try:
        values = [round(float(item), 2) for item in raw[:2]]
    except (TypeError, ValueError):
        return None
    return values if len(values) == 2 else None


def _tail(text: str, limit: int = 1200) -> str:
    return text[-limit:]
