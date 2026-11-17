"""OP-09 单测与端到端：语种规则、时间抽取、新鲜度、边界与幂等。"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from op09_env import CORE, OP02_EVIDENCE

lang = CORE.lang
timeparse = CORE.timeparse
load_config = CORE.load_config


def test_detect_zh_en_ja():
    cfg = load_config()
    zh = lang.detect("机器学习是人工智能的一个分支，用于从数据中学习规律。", cfg)
    assert zh["language"] == "zh"
    assert zh["status"] == "identified"
    assert zh["confidence"] >= 0.85

    en = lang.detect("Machine learning is a branch of artificial intelligence.", cfg)
    assert en["language"] == "en"
    assert en["status"] == "identified"

    ja = lang.detect("これは機械学習の説明です。データから規則を学びます。", cfg)
    assert ja["language"] == "ja"
    assert ja["status"] == "identified"


def test_detect_mixed_and_empty():
    cfg = load_config()
    mixed = lang.detect("机器学习 machine learning 是人工智能的重要分支 important branch", cfg)
    assert mixed["status"] in {"mixed", "unknown"}
    assert mixed["confidence"] < 0.85

    empty = lang.detect("   ", cfg)
    assert empty["language"] == "unknown"
    assert empty["reasonCode"] == "EMPTY_TEXT"


def test_time_extraction_priority():
    cfg = load_config()
    first = timeparse.extract("2024-03-05T00:00:00", "文中提到 2010 年", "2026-11-16", cfg)
    assert first["timeSource"] == "capturedAt"
    assert first["year"] == 2024
    assert first["quarter"] == 1

    second = timeparse.extract(None, "报告写于 2018 年，数据来自更早年份。", "2026-11-16", cfg)
    assert second["timeSource"] == "text_year"
    assert second["year"] == 2018

    third = timeparse.extract(None, "没有年份的正文", "2026-11-16", cfg)
    assert third["timeSource"] == "unknown"
    assert third["year"] is None

    fourth = timeparse.extract(None, "没有年份", None, cfg)
    assert fourth["timeSource"] == "unknown"
    assert fourth["year"] is None


def test_freshness_formula():
    cfg = load_config()
    as_of = date(2026, 12, 31)
    assert timeparse.freshness(2026, as_of, cfg) == 0.6
    assert timeparse.freshness(2024, as_of, cfg) == 0.3
    assert timeparse.freshness(2010, as_of, cfg) == 0.1
    assert timeparse.freshness(None, as_of, cfg) == 0.0


def _record(record_id: str, text: str | None, captured: str | None = None) -> dict:
    return {
        "record_id": record_id,
        "modal": "text",
        "source": "web_text",
        "text": text,
        "metadata": {"format": "txt", "capturedAt": captured},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": not (text or "").strip()},
        "partitions": {"modal": "text", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": None, "sha256": None, "simhash": None, "phash": None},
    }


def test_core_mixed_batch(tmp_path: Path):
    records = [
        _record("r1", "这是一段中文文本，用于测试语种识别。", "2025-05-01T00:00:00"),
        _record("r2", "This is an English sentence for testing."),
        _record("r3", "データから規則を学びます。"),
        _record("r4", "   "),
    ]
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8"
    )
    result = CORE.run(str(input_dir), {"as_of": "2026-12-31"}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert result["sampleCount"] == 4
    assert metrics["language"]["counts"]["zh"] == 1
    assert metrics["language"]["counts"]["en"] == 1
    assert metrics["language"]["counts"]["ja"] == 1
    assert metrics["language"]["counts"]["unknown"] == 1
    assert metrics["time"]["knownTimeRatio"] == 0.25
    assert metrics["region"]["status"] == "unavailable"
    assert metrics["time"]["freshnessMean"] is not None


def test_core_idempotent(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        json.dumps(_record("r1", "中文文本", "2025-01-01T00:00:00"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    CORE.run(str(input_dir), {}, 42, str(tmp_path / "a"))
    CORE.run(str(input_dir), {}, 42, str(tmp_path / "b"))
    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_core_real_op02_batch(tmp_path: Path):
    if not (OP02_EVIDENCE / "records.jsonl").is_file():
        import pytest

        pytest.skip("缺少 OP-02 证据目录")
    result = CORE.run(str(OP02_EVIDENCE), {}, 42, str(tmp_path / "real"))
    assert result["sampleCount"] == 432
    metrics = result["metrics"]
    assert sum(metrics["language"]["counts"].values()) == 432
    assert metrics["language"]["statusCounts"].get("identified", 0) > 400
    assert 0.0 <= metrics["language"]["confidenceMean"] <= 1.0
    assert metrics["time"]["timeSourceCounts"]
