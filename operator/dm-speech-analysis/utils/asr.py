"""FunASR paraformer-zh 转写（来源：OP-05 ``utils/asr.py`` 0.1.0 精简版，注明来源）。

权重 ``operator/weights/shared/paraformer-zh``（Apache-2.0），CPU，运行期不联网；
超过单次上限需平台分片，返回明确异常，不伪造文本。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .common import DependencyUnavailable, resolve_weights_dir

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
        _MODEL = AutoModel(model=str(model_dir), disable_update=True, disable_pbar=True, device="cpu")
    return _MODEL


def _duration(path: Path) -> float | None:
    import soundfile

    try:
        info = soundfile.info(str(path))
        return float(info.frames) / float(info.samplerate)
    except Exception:  # noqa: BLE001
        return None


def _split(source: Path, target_dir: Path, chunk_sec: int, timeout: int) -> list[Path]:
    chunks: list[Path] = []
    start = 0
    while start < int(_duration(source) or 0) + chunk_sec:
        output = target_dir / f"chunk_{start:06d}.wav"
        command = [
            "ffmpeg", "-v", "error", "-ss", str(start), "-t", str(chunk_sec),
            "-i", str(source), "-ar", "16000", "-ac", "1", "-y", str(output),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=timeout)
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            raise AsrFailed(f"ffmpeg 分片失败：{exc}") from exc
        if not output.is_file() or output.stat().st_size == 0:
            break
        chunks.append(output)
        start += chunk_sec
        if start > 60 * 60 * 4:
            break
    return chunks


def transcribe(path: str | Path, cfg: dict[str, Any]) -> dict[str, Any]:
    source = Path(path)
    duration = _duration(source)
    if duration is not None and duration > int(cfg["limits"]["maxAudioSeconds"]):
        raise AsrFailed(f"音频超过单次上限 {cfg['limits']['maxAudioSeconds']}s，需平台分片")
    model = _model(cfg)
    chunk_sec = int(cfg["limits"]["asrChunkSec"])
    if duration is not None and duration > chunk_sec:
        texts: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            for chunk in _split(source, Path(tmp), chunk_sec, 120):
                texts.append(_text_of(model.generate(input=str(chunk), batch_size=1)))
        text = " ".join(item for item in texts if item)
        return {"text": text, "segments": len(texts), "durationSec": duration}
    result = model.generate(input=str(source), batch_size=1)
    return {"text": _text_of(result), "segments": 1, "durationSec": duration}


def _text_of(result: Any) -> str:
    if not result:
        return ""
    first = result[0] if isinstance(result, list) else result
    if isinstance(first, dict):
        return str(first.get("text") or "")
    return str(first)
