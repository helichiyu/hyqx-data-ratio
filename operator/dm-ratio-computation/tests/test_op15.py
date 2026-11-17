"""OP-15 单测与端到端：权重链路、最大余数、校验单、极限用例与幂等。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from op15_env import CORE, OP02_EVIDENCE, OP05_EVIDENCE, REPO_ROOT

cfg = CORE.load_config()
weights = CORE.weights_util
checks = CORE.checks_util


def _rows(effects: list[float]) -> list[dict]:
    return [
        {"label": f"l{index}", "effectiveCount": value, "count": int(value), "level1": f"l{index}", "level2": f"l{index}"}
        for index, value in enumerate(effects)
    ]


def test_effective_count_formula():
    inventory = {"A": {"web_text": 10.0, "__chars__web_text": 500.0}, "B": {"books": 5.0}}
    rows = weights.compute_effective(inventory, {}, cfg)
    by_label = {row["label"]: row for row in rows}
    assert by_label["A"]["count"] == 10
    assert by_label["A"]["effectiveCount"] == 10.0
    assert by_label["B"]["effectiveCount"] == 5.0
    assert by_label["A"]["level1"] == "A"


def test_largest_remainder_sums_to_one():
    rows = _rows([1.0, 1.0, 1.0])
    result = weights.normalize(rows, cfg)
    assert result["sumUnits"] == result["unit"]
    assert abs(sum(row["share"] for row in rows) - 1.0) < 1e-12
    assert sorted(row["share"] for row in rows) == [0.3333, 0.3333, 0.3334]


def test_long_tail_not_zeroed():
    rows = _rows([1000.0, 1.0])
    weights.normalize(rows, cfg)
    assert rows[1]["share"] >= cfg["normalization"]["minShare"]
    assert abs(sum(row["share"] for row in rows) - 1.0) < 1e-9


def test_zero_weight_label_excluded():
    inventory = {"A": {"web_text": 10.0}, "B": {"web_text": 10.0}}
    rows = weights.compute_effective(inventory, {"A": 0.0}, cfg)
    weights.normalize(rows, cfg)
    by_label = {row["label"]: row for row in rows}
    assert by_label["A"]["effectiveCount"] == 0.0
    assert by_label["A"]["share"] == 0.0
    assert by_label["B"]["share"] == 1.0


def test_checks_pass_and_fail():
    tree_path = Path(__file__).resolve().parents[3] / "operator" / "baseline" / "tree-snapshot.json"
    tree = checks.load_tree(tree_path)
    rows = _rows([5.0, 5.0])
    normalization = weights.normalize(rows, cfg)
    report = checks.evaluate(rows, normalization, tree, cfg)
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["sum_100"]["passed"] is True
    assert by_id["level1_coverage"]["passed"] is False  # 只有 2 个一级类
    assert by_id["min_sample"]["passed"] is True
    assert by_id["inventory_gap"]["passed"] is False


def _record(record_id: str, text_chars: int = 10, source: str = "web_text") -> dict:
    return {
        "record_id": record_id,
        "modal": "text",
        "source": source,
        "text": "x" * text_chars,
        "metadata": {"format": "txt", "sizeBytes": text_chars},
        "quality": {"completeness": 1.0, "decodable": True, "emptyText": False},
        "partitions": {"modal": "text", "source": source, "dt": "2026-11-16"},
        "hashes": {"md5": None, "sha256": None, "simhash": None, "phash": None},
    }


def _label_rows() -> list[dict]:
    rows = []
    for index in range(10):
        rows.append({"record_id": f"r{index}", "labels": [{"path": ["新闻与资讯", "科技新闻", "产品发布与行业动态"]}]})
    for index in range(10, 15):
        rows.append({"record_id": f"r{index}", "labels": [{"path": ["教育", "教学与培训", "在线教育"]}]})
    rows.append({"record_id": "r15", "labels": [{"path": ["信息技术", "语言智能", "机器翻译"]}]})
    return rows


def test_core_ten_sample_extreme(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(_record(f"r{index}"), ensure_ascii=False) for index in range(16)) + "\n",
        encoding="utf-8",
    )
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()
    labels_file = labels_dir / "result.jsonl"
    labels_file.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in _label_rows()) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    result = CORE.run(
        str(input_dir),
        {"labels_path": str(labels_dir), "target_total": 10},
        42,
        str(tmp_path / "out"),
    )
    metrics = result["metrics"]
    assert metrics["labelCount"] == 3
    assert abs(metrics["shareSum"] - 1.0) <= 0.001
    assert metrics["feedTotal"] == 10
    by_id = {item["id"]: item for item in metrics["checks"]}
    assert by_id["sum_100"]["passed"] is True
    assert by_id["core_label_coverage"]["passed"] is True
    assert by_id["level1_coverage"]["passed"] is False
    assert by_id["inventory_gap"]["passed"] is True
    assert metrics["totalGap"] == 0


def test_core_without_labels(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        json.dumps(_record("r1"), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    assert result["metrics"]["labelCount"] == 0
    assert result["metrics"]["failedChecks"]


def test_core_idempotent(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(_record(f"r{index}"), ensure_ascii=False) for index in range(16)) + "\n",
        encoding="utf-8",
    )
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()
    (labels_dir / "result.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in _label_rows()) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    CORE.run(str(input_dir), {"labels_path": str(labels_dir)}, 42, str(tmp_path / "a"))
    CORE.run(str(input_dir), {"labels_path": str(labels_dir)}, 42, str(tmp_path / "b"))
    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_core_real_batch(tmp_path: Path, monkeypatch):
    if not (OP05_EVIDENCE / "result.jsonl").is_file():
        import pytest

        pytest.skip("缺少 OP-05 证据目录")
    monkeypatch.setenv("INPUT_DIR", str(REPO_ROOT / "operator"))
    result = CORE.run(
        str(OP02_EVIDENCE),
        {"labels_path": str(OP05_EVIDENCE)},
        42,
        str(tmp_path / "real"),
    )
    metrics = result["metrics"]
    assert metrics["labelCount"] > 0
    assert abs(metrics["shareSum"] - 1.0) <= 0.001
    assert metrics["normalizationError"] <= 0.001
