"""OP-08 端到端测试：真实 OP-02 记录、边界、幂等、领域缺失。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from op08_env import CORE, OP02_EVIDENCE


def _record(record_id: str, modal: str, text: str | None, size: int = 10) -> dict:
    sha = hashlib.sha256((text or record_id).encode("utf-8")).hexdigest()
    md5 = hashlib.md5((text or record_id).encode("utf-8"), usedforsecurity=False).hexdigest()
    return {
        "record_id": record_id,
        "modal": modal,
        "source": "web_text",
        "text": text,
        "metadata": {"format": "txt", "sizeBytes": size, "sha256": sha, "durationSec": 12.5 if modal in {"audio", "video"} else None, "frameCount": 25 if modal == "video" else None, "capturedAt": "2025-06-01T00:00:00"},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": not (text or "").strip()},
        "partitions": {"modal": modal, "source": "web_text", "dt": "2025-06-01"},
        "hashes": {"md5": md5, "sha256": sha, "simhash": None, "phash": None},
    }


def _write(path: Path, records: list[dict]) -> Path:
    target = path / "records.jsonl"
    target.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
        encoding="utf-8",
    )
    return target


def test_core_scale_and_source(tmp_path):
    records = [
        _record("r1", "text", "一二三四五"),
        _record("r2", "text", "abcdefghij", size=20),
        _record("r3", "audio", None, size=30),
        _record("r4", "video", None, size=40),
        _record("r5", "image", None, size=50),
    ]
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _write(input_dir, records)
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))

    assert result["sampleCount"] == 5
    assert result["successCount"] == 5
    assert result["failedCount"] == 0
    metrics = result["metrics"]
    assert metrics["scale"]["recordCount"] == 5
    assert metrics["scale"]["modalCounts"] == {"audio": 1, "image": 1, "text": 2, "video": 1}
    assert metrics["scale"]["textChars"] == 15
    assert metrics["scale"]["textBytes"] == len("一二三四五".encode()) + 10
    assert metrics["scale"]["durationSec"] == 25.0
    assert metrics["scale"]["frameCount"] == 25
    assert metrics["scale"]["sizeBytes"] == 150
    assert metrics["scale"]["percentiles"]["textChars"]["p50"] == 5.0
    assert metrics["scale"]["percentiles"]["textChars"]["p90"] == 10.0
    source = metrics["sourceDistribution"]
    assert source["shareSumPercent"] == 100.0
    assert source["classes"]["web_text"]["count"] == 5
    assert source["ahp"]["consistent"] is True
    assert metrics["domainCoverage"]["status"] == "unavailable"
    assert (tmp_path / "out" / "result.jsonl").is_file()


def test_core_empty_batch(tmp_path):
    input_dir = tmp_path / "empty"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text("", encoding="utf-8")
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    assert result["sampleCount"] == 0
    metrics = result["metrics"]
    assert metrics["scale"]["recordCount"] == 0
    assert metrics["scale"]["percentiles"]["textChars"]["p50"] is None
    assert metrics["scale"]["modalCounts"] == {}
    assert metrics["sourceDistribution"]["shareSumPercent"] == 0.0


def test_core_idempotent(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _write(input_dir, [_record("r1", "text", "同一批数据"), _record("r2", "text", "第二条")])
    first = CORE.run(str(input_dir), {}, 42, str(tmp_path / "a"))
    second = CORE.run(str(input_dir), {}, 42, str(tmp_path / "b"))
    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()
    assert first["metrics"]["scale"] == second["metrics"]["scale"]


def test_core_real_op02_batch(tmp_path):
    if not (OP02_EVIDENCE / "records.jsonl").is_file():
        import pytest

        pytest.skip("缺少 OP-02 证据目录")
    result = CORE.run(str(OP02_EVIDENCE), {}, 42, str(tmp_path / "real"))
    assert result["sampleCount"] == 432
    assert result["successCount"] == 432
    metrics = result["metrics"]
    assert metrics["scale"]["recordCount"] == 432
    assert metrics["scale"]["textChars"] > 0
    classes = metrics["sourceDistribution"]["classes"]
    assert sum(item["count"] for item in classes.values()) == 432
    assert all(name in classes for name in ("web_text", "books", "code", "science", "wiki", "dialogue"))
