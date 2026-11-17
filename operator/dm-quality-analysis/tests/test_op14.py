"""OP-14 单测与端到端：完整率、Gini、冲突、难度、极性、边界与幂等。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from op14_env import CORE, OP02_EVIDENCE

cfg = CORE.load_config()
gini = CORE.gini_util
completeness = CORE.completeness_util
conflict = CORE.conflict_util
difficulty = CORE.difficulty_util
polarity = CORE.polarity_util
labels = CORE.labels_util


def test_gini_known_sets():
    assert gini.coefficient([1, 1, 1, 1]) == 0.0
    assert gini.coefficient([10, 0, 0, 0]) == pytest_approx(0.75)
    assert gini.coefficient([]) is None
    report = gini.analyze({"a": 10, "b": 0, "c": 0, "d": 0}, cfg)
    assert report["exceedsThreshold"] is True


def pytest_approx(value):
    import pytest

    return pytest.approx(value, abs=1e-6)


def test_completeness():
    record = {
        "record_id": "r1",
        "modal": "text",
        "source": "web_text",
        "text": "有内容",
        "metadata": {"format": "txt", "sizeBytes": 10},
        "quality": {"decodable": True},
        "partitions": {"dt": "2026-11-16"},
        "hashes": {"md5": "a", "sha256": "b"},
    }
    report = completeness.evaluate(record, cfg)
    assert report["rate"] == 1.0
    assert report["missingFields"] == []

    broken = {**record, "metadata": {"format": "txt"}, "hashes": {}}
    report = completeness.evaluate(broken, cfg)
    assert report["rate"] < 1.0
    assert "metadata.sizeBytes" in report["missingFields"]
    assert "hashes.md5" in report["missingFields"]


def test_conflict_detects_near_duplicates():
    texts = [
        ("r1", "机器学习模型需要大量高质量的训练数据来完成特征表示与分类任务"),
        ("r2", "机器学习模型需要大量高质量的训练数据来完成特征表示与分类任务!"),
        ("r3", "完全不同的一段文本，讨论天气预报与航空运输管理"),
    ]
    report = conflict.analyze(texts, cfg)
    assert report["nearDuplicateGroups"] == 1
    assert report["conflictGroups"] == 1
    assert report["conflictRate"] == 1.0


def test_conflict_identical_not_difference():
    same = "完全相同的文本内容用于测试近重复分组逻辑"
    report = conflict.analyze([("r1", same), ("r2", same)], cfg)
    assert report["nearDuplicateGroups"] == 1
    assert report["conflictGroups"] == 0


def test_difficulty_bands():
    easy = difficulty.score(5.0, 1.0, 0.0, cfg)
    assert easy["level"] == "简单"
    hard = difficulty.score(100.0, 8.0, 1.0, cfg)
    assert hard["level"] == "困难"
    assert 0 <= easy["score"] < hard["score"] <= 100


def test_polarity_rule_and_negation():
    positive = polarity.analyze("模型效果良好，指标提升明显。", cfg)
    assert positive["polarity"] == "positive"
    negative = polarity.analyze("系统失败，存在严重缺陷与风险。", cfg)
    assert negative["polarity"] == "negative"
    negated = polarity.analyze("指标没有提升。", cfg)
    assert negated["polarity"] == "negative"
    neutral = polarity.analyze("今天开了一次会。", cfg)
    assert neutral["polarity"] == "neutral"


def test_labels_coverage_and_consistency(tmp_path: Path):
    path = tmp_path / "result.jsonl"
    rows = [
        {"record_id": "r1", "labels": [{"path": ["A", "a"]}]},
        {"record_id": "r2", "labels": []},
    ]
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n", encoding="utf-8")
    mapping = labels.load(path)
    coverage = labels.coverage(mapping, ["r1", "r2"])
    assert coverage["coverage"] == 0.5

    records = [
        {"record_id": "r3", "metadata": {"extra": {"derivedFrom": "r1"}}},
    ]
    mapping["r3"] = [["A", "b"]]
    consistency = labels.multimodal_consistency(records, mapping)
    assert consistency["status"] == "ok"
    assert consistency["consistency"] == 1.0


def _record(record_id: str, text: str, modal: str = "text") -> dict:
    return {
        "record_id": record_id,
        "modal": modal,
        "source": "web_text",
        "text": text if modal == "text" else None,
        "metadata": {"format": "txt", "sizeBytes": len((text or "").encode()), "extra": {}},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": not (text or "").strip()},
        "partitions": {"modal": modal, "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": "0" * 32, "sha256": "0" * 64},
    }


def test_core_without_labels(tmp_path: Path):
    records = [
        _record("r1", "机器学习模型需要大量高质量训练数据来完成分类任务。"),
        _record("r2", "机器学习模型需要大量高质量训练数据来完成分类任务！"),
        _record("r3", "   "),
        _record("r4", None, modal="image"),
    ]
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8"
    )
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert result["sampleCount"] == 4
    assert metrics["conflict"]["nearDuplicateGroups"] == 1
    assert metrics["gini"]["status"] == "unavailable"
    assert metrics["annotation"]["status"] == "unavailable"
    assert metrics["lowQualityCount"] >= 1
    assert metrics["polarity"]["counts"]


def test_core_idempotent(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        json.dumps(_record("r1", "同一批文本用于幂等校验。"), ensure_ascii=False) + "\n", encoding="utf-8"
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
    assert metrics["records"] == 432
    assert metrics["completeness"]["mean"] == 1.0
    assert metrics["conflict"]["nearDuplicateGroups"] >= 1
    assert metrics["difficulty"]["counts"]
