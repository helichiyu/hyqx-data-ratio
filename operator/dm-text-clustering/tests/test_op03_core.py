"""OP-03 端到端测试：真实 bge 向量、边界、幂等、依赖缺失。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from op03_env import CORE, OP02_EVIDENCE


def _record(record_id: str, text: str, modal: str = "text") -> dict:
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    md5 = hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()
    return {
        "record_id": record_id,
        "modal": modal,
        "source": "web_text",
        "text": text if modal == "text" else None,
        "metadata": {"format": "txt", "sizeBytes": len(text.encode()), "sha256": sha},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": not text.strip()},
        "partitions": {"modal": modal, "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": md5, "sha256": sha, "simhash": None, "phash": None},
    }


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
        encoding="utf-8",
    )


def test_core_vectors_and_idempotent(tmp_path):
    texts = [
        "机器学习是人工智能的一个分支，研究如何从数据中学习规律。",
        "深度学习使用多层神经网络进行特征表示与分类。",
        "自然语言处理研究计算机理解与生成人类语言。",
        "财经市场受利率、通胀和投资者情绪影响。",
        "股票价格波动反映市场供需与预期。",
        "宏观经济政策包括财政政策与货币政策。",
        "足球比赛需要团队配合与战术执行。",
        "篮球运动员需要良好的体能与投篮技术。",
        "奥运会汇集全球顶尖运动员。",
        "诗歌用凝练语言表达情感与意象。",
        "小说通过人物与情节展现社会生活。",
        "散文注重语言节奏与个人体验。",
    ]
    records = [_record(f"r_{index}", text) for index, text in enumerate(texts)]
    source = tmp_path / "records.jsonl"
    _write(source, records)

    first = CORE.run(str(source), params={"k": 3}, seed=42, output_dir=str(tmp_path / "a"))
    second = CORE.run(str(source), params={"k": 3}, seed=42, output_dir=str(tmp_path / "b"))
    assert first["sampleCount"] == 12
    assert first["successCount"] == 12
    assert first["failedCount"] == 0
    assert first["metrics"]["vectorDimension"] == 768
    assert first["metrics"]["k"] == 3

    vectors = np.load(tmp_path / "a" / "vectors.npy")
    assert vectors.shape == (12, 768)
    assert vectors.dtype == np.float16
    rows = [
        json.loads(line)
        for line in (tmp_path / "a" / "result.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(rows) == 12
    assert {row["cluster"] for row in rows} == {0, 1, 2}
    summary = json.loads((tmp_path / "a" / "cluster_summary.json").read_text(encoding="utf-8"))
    assert summary["k"] == 3
    assert all(cluster["topTerms"] for cluster in summary["clusters"])

    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()
    assert (tmp_path / "a" / "manifest.json").is_file()


def test_core_skips_non_text_and_empty(tmp_path):
    records = [
        _record("r_text", "一段可聚类的文本内容。"),
        _record("r_empty", ""),
        _record("r_image", "", modal="image"),
    ]
    source = tmp_path / "records.jsonl"
    _write(source, records)
    result = CORE.run(str(source), params={"k": 2}, seed=42, output_dir=str(tmp_path / "out"))
    assert result["sampleCount"] == 2
    assert result["successCount"] == 1
    assert result["failedCount"] == 1
    assert result["failedSamples"][0]["reasonCode"] == "EMPTY_TEXT"
    assert result["metrics"]["skippedNonText"] == 1


def test_core_missing_weights(tmp_path, monkeypatch):
    source = tmp_path / "records.jsonl"
    _write(source, [_record("r_1", "一段文本。")])
    monkeypatch.setenv("WEIGHTS_DIR", str(tmp_path / "no-weights"))
    with pytest.raises(CORE.embedder.DependencyUnavailable):
        CORE.run(str(source), params={"k": 2}, seed=42, output_dir=str(tmp_path / "out"))


@pytest.mark.skipif(not OP02_EVIDENCE.is_dir(), reason="缺少 S1 OP-02 证据目录")
def test_core_real_batch_subset(tmp_path):
    result = CORE.run(
        str(OP02_EVIDENCE),
        params={"max_records": 40, "k": 3},
        seed=42,
        output_dir=str(tmp_path / "real"),
    )
    assert 0 < result["successCount"] <= 40
    assert result["metrics"]["vectorDimension"] == 768
    assert (tmp_path / "real" / "vectors.npy").is_file()
    assert result["failedCount"] == 0
