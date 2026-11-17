"""OP-08 纯函数单测：AHP、分位数、来源分布、领域覆盖。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from op08_env import CORE

ahp = CORE.ahp
domain = CORE.domain
source = CORE.source
load_config = CORE.load_config
percentile_nearest_rank = CORE.percentile_nearest_rank


def test_ahp_weights_and_consistency():
    cfg = load_config()
    result = ahp.consistency(cfg["ahp"]["matrix"])
    assert result["n"] == 4
    assert result["cr"] < 0.1
    assert abs(sum(result["weights"]) - 1.0) < 1e-6
    for expected, actual in zip([0.4, 0.3, 0.2, 0.1], result["weights"]):
        assert abs(expected - actual) < 0.01


def test_ahp_inconsistent_matrix_detected():
    matrix = [
        [1, 5, 1 / 5, 1],
        [1 / 5, 1, 7, 1 / 3],
        [5, 1 / 7, 1, 2],
        [1, 3, 1 / 2, 1],
    ]
    result = ahp.consistency(matrix)
    assert result["cr"] > 0.1


def test_percentile_nearest_rank():
    values = [float(i) for i in range(1, 101)]
    assert percentile_nearest_rank(values, 50) == 50
    assert percentile_nearest_rank(values, 90) == 90
    assert percentile_nearest_rank(values, 99) == 99
    assert percentile_nearest_rank([], 50) is None
    assert percentile_nearest_rank([7.0], 99) == 7.0


def test_source_shares_sum_to_100():
    cfg = load_config()
    counts = {"web_text": 6, "books": 2, "code": 1, "science": 1}
    dts = {
        "web_text": ["2026-01-01"] * 6,
        "books": ["2019-01-01"] * 2,
        "code": ["2024-01-01"] * 1,
        "science": [None] * 1,
    }
    completeness = {name: [1.0] * count for name, count in counts.items()}
    report = source.class_scores(counts, dts, completeness, cfg, date(2026, 1, 1))
    assert abs(report["shareSumPercent"] - 100.0) < 1e-6
    assert report["ahp"]["consistent"] is True
    assert report["classes"]["web_text"]["freshnessDetail"]["buckets"]["last_1y"] == 6
    assert report["classes"]["books"]["freshnessDetail"]["buckets"]["older"] == 2
    assert report["classes"]["science"]["freshnessDetail"]["neutralUsed"] is True
    assert report["unexpectedSourceAliases"] == []


def test_domain_coverage_rollup(tmp_path: Path):
    tree_path = Path(__file__).resolve().parents[3] / "operator" / "baseline" / "tree-snapshot.json"
    tree = domain.load_tree(tree_path)
    assert tree["treeVersion"]
    assert len(tree["level1"]) == 16

    first = tree["level1"][0]
    second = tree["level1"][1]
    rows = [
        {"record_id": "r1", "domainLabels": [{"path": [first]}]},
        {"record_id": "r2", "domainLabels": [{"path": [first]}, {"path": [second]}]},
        {"record_id": "r3", "domainLabels": []},
    ]
    path = tmp_path / "domain.jsonl"
    path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n", encoding="utf-8"
    )
    report = domain.domain_coverage(path, tree, text_records=3)
    assert report["status"] == "ok"
    assert report["level1"]["covered"] == 2
    assert report["coverage"]["labeledRecordRate"] == pytest.approx(2 / 3, abs=1e-6)
    assert second in report["level1"]["counts"]
    assert len(report["level1"]["missing"]) == 14


def test_domain_unavailable_without_labels():
    tree_path = Path(__file__).resolve().parents[3] / "operator" / "baseline" / "tree-snapshot.json"
    tree = domain.load_tree(tree_path)
    report = domain.domain_coverage(None, tree, text_records=1)
    assert report["status"] == "unavailable"
    assert report["reasonCode"] == "DOMAIN_LABELS_UNAVAILABLE"
