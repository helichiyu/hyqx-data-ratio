"""FunASR paraformer-zh 中文语音转写。

权重 ``operator/weights/shared/paraformer-zh``（Apache-2.0），运行期不联网。
设备优先级 ``DEVICE`` > 配置 > auto（CUDA 可用则 ``cuda:0``，否则 CPU）；
长音频按 ``asrChunkSec`` 切片后逐段转写；失败返回明确异常。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .common import DependencyUnavailable, resolve_device, resolve_weights_dir

_MODEL = None


class AsrFailed(RuntimeError):
    """ASR 执行失败。"""


def _model(cfg: dict[str, Any]):
    global _MODEL
    if _MODEL is None:
        model_dir = resolve_weights_dir() / cfg["media"]["asrModelRelativePath"]
        if not (model_dir / "model.pt").is_file():
            raise DependencyUnavailable(f"ASR 权重缺失：{model_dir}")
        try:
            from funasr import AutoModel
        except ImportError as exc:  # pragma: no cover
            raise DependencyUnavailable(f"funasr 不可用：{exc}") from exc
        model_cfg = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
        _MODEL = AutoModel(
            model=str(model_dir),
            disable_update=True,
            disable_pbar=True,
            device=resolve_device(model_cfg.get("device")),
        )
    return _MODEL


def _duration(path: Path) -> float | None:
    import soundfile

    try:
        info = soundfile.info(str(path))
        return float(info.frames) / float(info.samplerate)
    except Exception:  # noqa: BLE001 - 时长不可得时不分片
        return None


def transcribe(path: str | Path, cfg: dict[str, Any], *, max_seconds: int) -> dict[str, Any]:
    source = Path(path)
    duration = _duration(source)
    if duration is not None and duration > max_seconds:
        raise AsrFailed(f"音频超过单次上限 {max_seconds}s（实际 {duration:.1f}s），需平台分片")
    chunk_sec = int(cfg["limits"]["asrChunkSec"])
    model = _model(cfg)

    if duration is not None and duration > chunk_sec:
        texts: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            chunks = _split(source, Path(tmp), chunk_sec, int(cfg["limits"]["ffmpegTimeoutSec"]))
            for chunk in chunks:
                result = model.generate(input=str(chunk), batch_size=1)
                texts.append(_text_of(result))
        text = " ".join(item for item in texts if item)
        return {"text": text, "chars": len(text), "segments": len(texts), "durationSec": duration}

    result = model.generate(input=str(source), batch_size=1)
    text = _text_of(result)
    return {"text": text, "chars": len(text), "segments": 1, "durationSec": duration}


def _text_of(result: Any) -> str:
    if not result:
        return ""
    first = result[0] if isinstance(result, list) else result
    if isinstance(first, dict):
        return str(first.get("text") or "").strip()
    return str(first).strip()


def _split(source: Path, out_dir: Path, chunk_sec: int, timeout: int) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AsrFailed("ffmpeg 不可用，无法切分长音频")
    chunks: list[Path] = []
    index = 0
    while True:
        target = out_dir / f"chunk_{index:04d}.wav"
        completed = subprocess.run(
            [
                ffmpeg, "-y", "-v", "error", "-ss", str(index * chunk_sec),
                "-t", str(chunk_sec), "-i", str(source),
                "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target),
            ],
            capture_output=True, timeout=timeout, check=False,
        )
        if completed.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
            break
        chunks.append(target)
        index += 1
        if index > 1000:
            break
    if not chunks:
        raise AsrFailed("音频切分失败")
    return chunks
