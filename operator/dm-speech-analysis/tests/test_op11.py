"""OP-11 单测与端到端：WER/CER、VAD/基频、无参考、FakeASR 流程与真实音频。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from op11_env import CORE, OP02_EVIDENCE

cfg = CORE.load_config()
wer = CORE.wer
acoustic = CORE.acoustic


def test_wer_cer_known_values():
    result = wer.measure("你好世界", "你好世界")
    assert result["wer"] == 0.0 and result["cer"] == 0.0
    result = wer.measure("你好世", "你好世界")
    assert result["cer"] == 0.25
    english = wer.measure("the quick brown fox", "the quick brown fox jumps")
    assert english["wer"] == 0.2
    missing = wer.measure("任意", None)
    assert missing["wer"] is None
    assert missing["reasonCode"] == "REFERENCE_TEXT_REQUIRED"


def _wav(path: Path, segments: list[tuple[float, float, float]], rate: int = 16000) -> None:
    import soundfile

    samples = []
    for seconds, amplitude, frequency in segments:
        count = int(seconds * rate)
        time_axis = np.arange(count) / rate
        samples.append((amplitude * np.sin(2 * np.pi * frequency * time_axis)).astype(np.float32))
    soundfile.write(str(path), np.concatenate(samples), rate)


def test_acoustic_vad_and_pitch(tmp_path: Path):
    path = tmp_path / "tone.wav"
    _wav(path, [(1.0, 0.5, 440.0), (1.0, 0.0, 440.0), (1.0, 0.5, 440.0)])
    stats = acoustic.analyze(path, cfg, transcript_chars=30)
    assert 0.5 <= stats["speechRatio"] <= 0.8
    assert stats["silenceRatio"] > 0.2
    assert stats["speechSec"] > 1.5
    assert stats["pitchMeanHz"] is not None
    assert 150 <= stats["pitchMeanHz"] <= 500
    assert stats["accent"]["status"] == "unavailable"


def _audio_record(record_id: str) -> dict:
    return {
        "record_id": record_id,
        "modal": "audio",
        "source": "web_text",
        "text": None,
        "metadata": {"format": "wav", "sizeBytes": 100, "durationSec": 3.0},
        "quality": {"completeness": 1.0, "decodable": True, "emptyText": True},
        "partitions": {"modal": "audio", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": None, "sha256": None, "simhash": None, "phash": None},
    }


def test_core_flow_with_stub_asr(tmp_path: Path, monkeypatch):
    """FakeASR 仅验证流程，不作为验收证据。"""

    input_dir = tmp_path / "input"
    (input_dir / "standard" / "audio").mkdir(parents=True)
    (input_dir / "records.jsonl").write_text(
        json.dumps(_audio_record("r1"), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _wav(input_dir / "standard" / "audio" / "r1.wav", [(1.5, 0.4, 220.0), (1.5, 0.0, 220.0)])
    monkeypatch.setattr(CORE.asr, "transcribe", lambda path, config: {"text": "测试语音", "segments": 1})

    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert metrics["audioRecords"] == 1
    assert metrics["processedRecords"] == 1
    assert metrics["werStatus"] == "unavailable"
    assert metrics["lowQualityCount"] == 0
    row = json.loads((tmp_path / "out" / "result.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["transcription"] == "测试语音"
    assert row["wer"] is None


def test_core_missing_media(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        json.dumps(_audio_record("r404"), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    assert result["metrics"]["failuresByReason"] == {"STANDARD_MEDIA_MISSING": 1}


def test_core_real_audio(tmp_path: Path):
    if not (OP02_EVIDENCE / "standard" / "audio").is_dir():
        import pytest

        pytest.skip("缺少 OP-02 标准音频")
    if not (Path("operator/weights/shared/paraformer-zh") / "model.pt").is_file():
        import pytest

        pytest.skip("缺少 paraformer 权重")
    result = CORE.run(str(OP02_EVIDENCE), {}, 42, str(tmp_path / "real"))
    metrics = result["metrics"]
    assert metrics["audioRecords"] == 3
    assert metrics["processedRecords"] >= 1
    assert metrics["transcribedRecords"] >= 1
    assert metrics["speechRatioMean"] is not None
