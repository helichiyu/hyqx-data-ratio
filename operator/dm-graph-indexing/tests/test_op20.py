"""OP-20 单测：规则抽取、图谱计数、索引幂等、检索可复现、服务状态。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from op20_env import CORE

cfg = CORE.load_config()


def _fixture(tmp_path: Path, with_vectors: bool = True) -> tuple[Path, Path, Path | None]:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    records = [
        {"record_id": "r1", "text": "2024-03-01 中国科学院 发布“量子计算”成果 123 项", "modal": "text", "source": "science",
         "partitions": {"modal": "text", "source": "science", "dt": "2024-03-01"}},
        {"record_id": "r2", "text": "清华大学 与 华为公司 在 2025年5月 开展合作", "modal": "text", "source": "web_text",
         "partitions": {"modal": "text", "source": "web_text", "dt": "2025-05-01"}},
        {"record_id": "r3", "text": "无实体短文本", "modal": "text", "source": "web_text",
         "partitions": {"modal": "text", "source": "web_text", "dt": "2025-05-01"}},
    ]
    (input_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n", encoding="utf-8"
    )
    labels = [
        {"record_id": "r1", "labels": [{"path": ["知识与参考", "科普与专著", "学术专著"], "confidence": 0.9}]},
        {"record_id": "r2", "labels": [{"path": ["代码与技术文档", "技术文档与手册", "API文档"], "confidence": 0.8}]},
    ]
    (input_dir / "labels.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in labels) + "\n", encoding="utf-8"
    )
    if not with_vectors:
        return input_dir / "records.jsonl", input_dir / "labels.jsonl", None
    vectors_dir = input_dir / "vectors"
    vectors_dir.mkdir()
    dimension = int(cfg["vector"]["dimension"])
    matrix = np.arange(6 * dimension, dtype=np.float32).reshape(6, dimension) + 1.0
    np.save(vectors_dir / "vectors.npy", matrix)
    ids = [{"record_id": f"r{index + 1}", "row": index} for index in range(6)]
    (vectors_dir / "vector_ids.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in ids) + "\n", encoding="utf-8"
    )
    return input_dir / "records.jsonl", input_dir / "labels.jsonl", vectors_dir


def test_graph_and_index(tmp_path: Path, monkeypatch):
    records_path, labels_path, vectors_path = _fixture(tmp_path)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(
        str(records_path),
        {"records_path": str(records_path), "labels_path": str(labels_path), "vectors_path": str(vectors_path)},
        42,
        str(tmp_path / "out"),
    )
    metrics = result["metrics"]
    assert metrics["graph"]["recordCount"] == 3
    assert metrics["graph"]["labelCount"] >= 2
    assert metrics["graph"]["entityCount"] >= 4
    assert metrics["graph"]["edgeCount"] > 0
    assert metrics["vector"]["count"] == 6
    assert 0.0 <= metrics["vector"]["recallAtK"]["10"] <= 1.0
    assert metrics["services"]["neo4j"]["status"] == "unavailable"
    assert (tmp_path / "out" / "neo4j_import.cypher").is_file()
    assert (tmp_path / "out" / "query_results.jsonl").is_file()
    assert len((tmp_path / "out" / "graph_nodes.jsonl").read_text(encoding="utf-8").splitlines()) == metrics["graph"]["nodeCount"]


def test_index_deterministic(tmp_path: Path, monkeypatch):
    records_path, labels_path, vectors_path = _fixture(tmp_path)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    params = {"records_path": str(records_path), "labels_path": str(labels_path), "vectors_path": str(vectors_path)}
    CORE.run(str(records_path), params, 42, str(tmp_path / "a"))
    CORE.run(str(records_path), params, 42, str(tmp_path / "b"))
    left = (tmp_path / "a" / "graph_nodes.jsonl").read_bytes()
    right = (tmp_path / "b" / "graph_nodes.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()
    left = (tmp_path / "a" / "index" / "meta.json").read_bytes()
    right = (tmp_path / "b" / "index" / "meta.json").read_bytes()
    assert json.loads(left)["indexVersion"] == json.loads(right)["indexVersion"]


def test_blocked_without_vectors(tmp_path: Path, monkeypatch):
    records_path, labels_path, _ = _fixture(tmp_path, with_vectors=False)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(
        str(records_path),
        {"records_path": str(records_path), "labels_path": str(labels_path)},
        42,
        str(tmp_path / "out"),
    )
    assert result["blockedReason"] == "VECTORS_REQUIRED"
