"""OP-02 端到端测试：消费 OP-01 真实产物、标准产物可读、幂等、失败 reasonCode。"""

from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path

import pyarrow.parquet as pq



def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_records(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")


def test_consumes_op01_real_products(op1, op2, samples, tmp_path):
    op1_out = tmp_path / "op01"
    op1.run(
        str(samples / "mixed" / "mixed_batch_2026-11-16.zip"),
        params={},
        seed=42,
        output_dir=str(op1_out),
    )
    result = op2.run(str(op1_out), params={}, seed=42, output_dir=str(tmp_path / "op02"))
    assert result["sampleCount"] == result["successCount"] == 429
    assert result["failedCount"] == 0

    metrics = result["metrics"]
    assert metrics["standardized"] == {"text": 425, "images": 1, "audio": 2, "video": 1}
    assert metrics["parquet"]["rows"] == 429
    assert metrics["dedup"]["duplicateRecords"] >= 1
    assert metrics["associations"]["multiModalGroups"] >= 1
    assert metrics["decodeCheck"]["failed"] == []

    out = tmp_path / "op02"
    parquet_files = sorted((out / "standard" / "parquet").rglob("*.parquet"))
    assert parquet_files
    rows = sum(pq.read_table(path).num_rows for path in parquet_files)
    assert rows == 429
    index_rows = pq.read_table(out / "index" / "metadata.parquet").num_rows
    assert index_rows == 429

    waveforms = list((out / "standard" / "audio").glob("*.wav"))
    assert waveforms
    with wave.open(str(waveforms[0]), "rb") as handle:
        assert handle.getframerate() == 16000
        assert handle.getnchannels() == 1
    assert list((out / "standard" / "images").glob("*.webp"))
    assert list((out / "standard" / "video").glob("*.mp4"))


def test_idempotent_and_manifest_consistent(op1, op2, samples, tmp_path):
    op1_out = tmp_path / "op01"
    op1.run(
        str(samples / "mixed" / "mixed_batch_2026-11-16.zip"),
        params={},
        seed=42,
        output_dir=str(op1_out),
    )
    first = op2.run(str(op1_out), params={}, seed=42, output_dir=str(tmp_path / "a"))
    second = op2.run(str(op1_out), params={}, seed=42, output_dir=str(tmp_path / "b"))
    left = (tmp_path / "a" / "records.jsonl").read_bytes()
    right = (tmp_path / "b" / "records.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()

    manifest = json.loads((tmp_path / "a" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sampleCount"] == manifest["successCount"] + manifest["failedCount"]
    assert manifest["operatorId"] == "dm-corpus-normalization"
    assert len(manifest["runId"]) == 16
    assert manifest["runId"] != first["metrics"]["upstream"]["runId"]
    for artifact in manifest["artifacts"]:
        path = Path(artifact["path"])
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_minimal_records_file_contract(op2, tmp_path):
    text = "数据配比中心 S1 契约测试"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    md5 = hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()
    record = {
        "record_id": "r_contract",
        "modal": "text",
        "source": "web_text",
        "text": text,
        "metadata": {"format": "txt", "sizeBytes": len(text.encode()), "sha256": sha, "md5": md5},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": False},
        "partitions": {"modal": "text", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": md5, "sha256": sha, "simhash": None, "phash": None},
    }
    records = tmp_path / "records.jsonl"
    _write_records(records, record)
    result = op2.run(str(records), params={}, seed=42, output_dir=str(tmp_path / "out"))
    assert result["sampleCount"] == result["successCount"] == 1
    assert result["failedCount"] == 0
    assert result["outputFilePath"].endswith("records.jsonl")
    assert list((tmp_path / "out" / "standard" / "parquet").rglob("*.parquet"))


def test_missing_records_and_missing_source(op2, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = op2.run(str(empty), params={}, seed=42, output_dir=str(tmp_path / "empty_out"))
    assert result["failedCount"] == 1
    assert result["failedSamples"][0]["reasonCode"] == "RECORDS_NOT_FOUND"

    sha = "f" * 64
    record = {
        "record_id": "r_missing_src",
        "modal": "image",
        "source": "web_text",
        "text": None,
        "metadata": {
            "format": "jpeg",
            "sizeBytes": 10,
            "sha256": sha,
            "extra": {"file": "nope.jpg"},
        },
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": False},
        "partitions": {"modal": "image", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": "0" * 32, "sha256": sha, "simhash": None, "phash": None},
    }
    records = tmp_path / "missing.jsonl"
    _write_records(records, record)
    result = op2.run(str(records), params={}, seed=42, output_dir=str(tmp_path / "missing_out"))
    assert result["successCount"] == 0
    assert result["failedSamples"][0]["reasonCode"] == "SOURCE_FILE_MISSING"


def test_duplicates_and_anomalies_are_reported(op2, tmp_path):
    text = "重复文本内容"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    md5 = hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()
    base = {
        "modal": "text",
        "source": "web_text",
        "text": text,
        "metadata": {"format": "txt", "sizeBytes": len(text.encode()), "sha256": sha, "md5": md5},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": False},
        "partitions": {"modal": "text", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": md5, "sha256": sha, "simhash": None, "phash": None},
    }
    records = tmp_path / "dup.jsonl"
    records.write_text(
        "\n".join(
            json.dumps({**base, "record_id": f"r_{index}"}, ensure_ascii=False)
            for index in range(3)
        )
        + "\n",
        encoding="utf-8",
    )
    result = op2.run(str(records), params={}, seed=42, output_dir=str(tmp_path / "dup_out"))
    groups = _read_jsonl(tmp_path / "dup_out" / "duplicates.jsonl")
    assert result["metrics"]["dedup"]["duplicateRecords"] == 2
    assert groups[0]["kind"] == "exact"
    assert groups[0]["count"] == 3
