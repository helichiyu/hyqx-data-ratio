"""OP-01 端到端测试：真实样例、Schema、幂等、失败 reasonCode。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest



def _read_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_text_batch_schema_and_idempotent(core, samples, record_schema, manifest_schema, tmp_path):
    source = samples / "text" / "machine_learning.jsonl"
    first = core.run(str(source), params={}, seed=42, output_dir=str(tmp_path / "run1"))
    second = core.run(str(source), params={}, seed=42, output_dir=str(tmp_path / "run2"))

    assert first["sampleCount"] == first["successCount"] == 425
    assert first["failedCount"] == 0
    records = _read_records(Path(first["outputFilePath"]))
    for record in records:
        jsonschema.validate(record, record_schema)
    manifest = json.loads((tmp_path / "run1" / "manifest.json").read_text(encoding="utf-8"))
    jsonschema.validate(manifest, manifest_schema)
    assert manifest["sampleCount"] == manifest["successCount"] + manifest["failedCount"]

    left = Path(first["outputFilePath"]).read_bytes()
    right = Path(second["outputFilePath"]).read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_mixed_archive_split_and_schema(core, samples, record_schema, tmp_path):
    archive = samples / "mixed" / "mixed_batch_2026-11-16.zip"
    result = core.run(str(archive), params={}, seed=42, output_dir=str(tmp_path / "mixed"))
    records = _read_records(Path(result["outputFilePath"]))
    modalities = {record["modal"] for record in records}
    assert modalities == {"text", "image", "audio", "video"}
    assert result["failedCount"] == 0
    for record in records:
        jsonschema.validate(record, record_schema)

    split = json.loads((tmp_path / "mixed" / "split_manifest.json").read_text(encoding="utf-8"))
    archive_entry = next(item for item in split["entries"] if item.get("kind") == "archive")
    assert len(archive_entry["members"]) == 4
    audio_streams = [
        stream
        for item in split["entries"]
        for stream in item.get("streams", [])
        if stream["type"] == "audio_stream"
    ]
    assert audio_streams and audio_streams[0].get("derivedFrom")


def test_pdf_scanned_pages_are_not_fabricated(core, samples, tmp_path):
    pdf = samples / "pdf" / "noches_blancas_1905.pdf"
    result = core.run(str(pdf), params={}, seed=42, output_dir=str(tmp_path / "pdf"))
    assert result["successCount"] == 1
    assert result["metrics"]["pdf"]["scannedPages"] > 0
    assert result["metrics"]["pdf"]["ocrStatus"] == "unavailable"
    record = _read_records(Path(result["outputFilePath"]))[0]
    assert "OCR_BACKEND_UNAVAILABLE" in record["quality"]["notes"]
    assert 0 < record["quality"]["completeness"] < 1


def test_video_audio_stream_is_split(core, samples, tmp_path):
    video = samples / "video" / "60b5695ab2f0_with_audio.mp4"
    result = core.run(
        str(video), params={"max_keyframes": 5}, seed=42, output_dir=str(tmp_path / "video")
    )
    records = _read_records(Path(result["outputFilePath"]))
    assert {record["modal"] for record in records} == {"video", "audio"}
    video_record = next(record for record in records if record["modal"] == "video")
    audio_record = next(record for record in records if record["modal"] == "audio")
    assert video_record["metadata"]["extra"]["keyframeCount"] >= 1
    assert audio_record["metadata"]["extra"]["derivedFrom"] == video_record["record_id"]
    assert result["sampleCount"] == 2


def test_failures_have_reason_codes(core, tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"this is not an image")
    result = core.run(str(broken), params={}, seed=42, output_dir=str(tmp_path / "out"))
    assert result["successCount"] == 0
    assert result["failedCount"] == 1
    assert result["failedSamples"][0]["reasonCode"] == "DECODE_FAILED"

    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "unknown.bin").write_bytes(b"\x00\x01\x02")
    (batch / "note.txt").write_text("正常文本", encoding="utf-8")
    result = core.run(str(batch), params={}, seed=42, output_dir=str(tmp_path / "batch_out"))
    reasons = {item["reasonCode"] for item in result["failedSamples"]}
    assert "UNSUPPORTED_FILE_TYPE" in reasons
    assert result["sampleCount"] == result["successCount"] + result["failedCount"]


def test_empty_directory_and_archive_safety(core, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = core.run(str(empty), params={}, seed=42, output_dir=str(tmp_path / "empty_out"))
    assert result["sampleCount"] == 0
    assert result["successCount"] == 0
    assert result["failedCount"] == 0
    assert Path(result["outputFilePath"]).exists()

    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip")
    result = core.run(str(bad_zip), params={}, seed=42, output_dir=str(tmp_path / "zip_out"))
    assert result["failedCount"] == 1
    assert result["failedSamples"][0]["reasonCode"] == "ZIP_INVALID"


@pytest.mark.parametrize(
    "relative",
    ["image/530384988814704640.jpg", "audio/asr_example_hotword.wav"],
)
def test_media_attributes_are_real(core, samples, tmp_path, relative):
    result = core.run(
        str(samples / relative), params={}, seed=42, output_dir=str(tmp_path / "media")
    )
    record = _read_records(Path(result["outputFilePath"]))[0]
    if record["modal"] == "image":
        assert record["metadata"]["width"] > 0
        assert record["hashes"]["phash"]
    else:
        assert record["metadata"]["durationSec"] > 0
        assert record["metadata"]["extra"]["vad"]["frames"] > 0
