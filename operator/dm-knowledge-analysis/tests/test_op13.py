"""OP-13 单测与端到端：AC 匹配、知识密度、类型占比、热点窗口、无词表边界与幂等。"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from op13_env import CORE, OP02_EVIDENCE

cfg = CORE.load_config()
terms = CORE.terms_util
style = CORE.style_util
timewin = CORE.timewin


def test_automaton_matches_all_terms():
    automaton = terms.Automaton(["机器学习", "学习", "数据"])
    hits = automaton.find("机器学习使用数据")
    assert "机器学习" in hits
    assert "学习" in hits
    assert "数据" in hits


def test_term_analysis_coverage_and_density():
    glossary = {"机器学习": "ai", "数据": "ai", "训练": "ai", "模型": "ai"}
    automaton = terms.Automaton(list(glossary))
    report = terms.analyze("机器学习需要数据与训练", automaton, glossary)
    assert report["status"] == "ok"
    assert report["hitCount"] == 3
    assert report["coverage"] == 0.75
    assert report["densityPer100Chars"] is not None


def test_terms_unavailable_without_glossary():
    report = terms.analyze("任意文本", None, {})
    assert report["status"] == "unavailable"
    assert report["reasonCode"] == "GLOSSARY_UNAVAILABLE"


def test_knowledge_type_shares_sum_to_one():
    report = style.classify_knowledge("统计数据显示增长，因为需求提升，所以结论成立。", cfg)
    assert report["type"] in {"fact", "reasoning"}
    assert abs(sum(report["shares"].values()) - 1.0) < 1e-6
    unknown = style.classify_knowledge("今天开会。", cfg)
    assert unknown["type"] == "unknown"


def test_style_and_time_window():
    academic = style.classify_style("本文参考文献中列出研究表明。", cfg)
    assert academic["style"] == "academic"
    assert timewin.classify(2026, date(2026, 12, 31), 365) == "hot"
    assert timewin.classify(2020, date(2026, 12, 31), 365) == "long_tail"
    assert timewin.classify(None, date(2026, 12, 31), 365) == "unknown"


def _record(record_id: str, text: str) -> dict:
    return {
        "record_id": record_id,
        "modal": "text",
        "source": "web_text",
        "text": text,
        "metadata": {"format": "txt", "capturedAt": "2025-05-01T00:00:00"},
        "quality": {"completeness": 1.0, "decodable": True, "emptyText": not text.strip()},
        "partitions": {"modal": "text", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": None, "sha256": None, "simhash": None, "phash": None},
    }


def test_core_without_glossary(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in (_record("r1", "统计数据显示增长。"), _record("r2", "   "))
        )
        + "\n",
        encoding="utf-8",
    )
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert metrics["terms"]["status"] == "unavailable"
    assert metrics["entityCoverage"]["status"] == "unavailable"
    assert metrics["knowledgeTypes"]["counts"]
    assert metrics["hotspot"]["counts"]["hot"] == 1
    assert metrics["failuresByReason"] == {"EMPTY_TEXT": 1}


def test_core_idempotent(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        json.dumps(_record("r1", "同一文本用于幂等。"), ensure_ascii=False) + "\n", encoding="utf-8"
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
    metrics = result["metrics"]
    assert metrics["textRecords"] == 426
    assert metrics["evaluatedRecords"] > 400
    assert metrics["styles"]["counts"]
    assert metrics["terms"]["status"] == "unavailable"
