"""OP-19 单测：九维聚合、缺数据、综合分复算、渲染失败隔离。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from op19_env import CORE

cfg = CORE.load_config()


def _write_metrics(root: Path, op_id: str, payload: dict) -> Path:
    directory = root / op_id
    directory.mkdir(parents=True)
    (directory / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory


def _fixture(tmp_path: Path, omit: set[str] | None = None) -> dict[str, str]:
    omit = omit or set()
    root = tmp_path / "results"
    payloads = {
        "OP-05": {"pathLegalRate": 1.0, "labeledRate": 0.65, "operatorVersion": "0.1.0", "treeVersion": "t1"},
        "OP-07": {"legalRate": 1.0, "unclassifiedRecords": 154, "illegalLabels": 0, "operatorVersion": "0.1.0", "treeVersion": "t1"},
        "OP-08": {
            "sourceDistribution": {
                "classes": {
                    "web_text": {"count": 200, "sharePercent": 50.0},
                    "books": {"count": 80, "sharePercent": 20.0},
                    "code": {"count": 20, "sharePercent": 5.0},
                    "science": {"count": 60, "sharePercent": 15.0},
                    "wiki": {"count": 30, "sharePercent": 7.5},
                    "dialogue": {"count": 10, "sharePercent": 2.5},
                },
                "shareSumPercent": 100.0,
            },
            "domainCoverage": {"coverage": {"level1": 0.9, "level2": 0.6, "leaf": 0.3}},
            "scale": {"recordCount": 400},
            "operatorVersion": "0.1.0",
            "treeVersion": "t1",
        },
        "OP-09": {
            "time": {"freshnessMean": 0.6, "knownTimeRatio": 0.8, "staleShare": 0.3},
            "language": {"statusCounts": {"identified": 400}},
            "region": {"status": "unavailable"},
            "operatorVersion": "0.1.0",
            "treeVersion": "t1",
        },
        "OP-10": {
            "distributions": {"overall": {"p50": 6.0, "p90": 7.0}},
            "lowFitCount": 4,
            "evaluatedRecords": 400,
            "operatorVersion": "0.1.0",
            "treeVersion": "t1",
        },
        "OP-14": {
            "completeness": {"mean": 1.0},
            "gini": {"gini": 0.5},
            "polarity": {"balance": 0.9},
            "conflict": {"nearDuplicateGroups": 4, "conflictRate": 0.0},
            "operatorVersion": "0.1.0",
            "treeVersion": "t1",
        },
        "OP-15": {"checksPassed": 5, "checksTotal": 6, "failedChecks": ["inventory_gap"], "operatorVersion": "0.1.2"},
        "OP-17": {
            "duplicateRecords": 0,
            "dataset": {"rows": 278},
            "selectedCount": 278,
            "selectionRate": 0.5,
            "inventoryGap": 100,
            "operatorVersion": "0.1.0",
        },
        "OP-18": {
            "score": {"score": 0.8, "grade": "good"},
            "truth": {"status": "unavailable", "blockedReason": "TRUTH_REQUIRED"},
            "proxy": {"pathLegalityRate": 1.0},
            "compliance": {"status": "unavailable"},
            "operatorVersion": "0.1.0",
            "treeVersion": "t1",
        },
    }
    results = {}
    for op_id, payload in payloads.items():
        if op_id in omit:
            continue
        results[op_id] = str(_write_metrics(root, op_id, payload))
    return results


def test_nine_dimensions_and_overall(tmp_path: Path, monkeypatch):
    results = _fixture(tmp_path)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(str(tmp_path / "results"), {"operator_results": results}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert metrics["dimensionsTotal"] == 9
    assert metrics["dimensionsAvailable"] == 9
    package = json.loads((tmp_path / "out" / "report_package.json").read_text(encoding="utf-8"))
    dimensions = {item["key"]: item for item in package["dimensions"]}
    assert dimensions["scale_source"]["score"] is not None
    assert dimensions["domain_coverage"]["score"] == pytest.approx(0.9)
    assert dimensions["text_taskfit"]["score"] == pytest.approx(0.6)
    assert dimensions["ratio_compliance"]["score"] == pytest.approx(5 / 6)
    assert dimensions["assembly_integrity"]["score"] == pytest.approx(1.0)
    expected = sum(item["score"] * item["weight"] for item in package["dimensions"]) / sum(
        item["weight"] for item in package["dimensions"]
    )
    assert package["overall"]["score"] == pytest.approx(expected)
    assert (tmp_path / "out" / "report.html").is_file()
    assert package["render"]["status"] == "ok"


def test_missing_dimension_no_data(tmp_path: Path, monkeypatch):
    results = _fixture(tmp_path, omit={"OP-10"})
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(str(tmp_path / "results"), {"operator_results": results}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert "text_taskfit" in [item["key"] for item in metrics["missing"]]
    package = json.loads((tmp_path / "out" / "report_package.json").read_text(encoding="utf-8"))
    dimension = next(item for item in package["dimensions"] if item["key"] == "text_taskfit")
    assert dimension["status"] == "no_data"
    assert dimension["score"] is None
    assert package["overall"]["dimensionsAvailable"] == 8


def test_render_failure_does_not_break_package(tmp_path: Path, monkeypatch):
    results = _fixture(tmp_path)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

    def boom(*_args, **_kwargs):
        raise RuntimeError("render boom")

    monkeypatch.setattr(CORE.score_util, "render_html", boom)
    result = CORE.run(str(tmp_path / "results"), {"operator_results": results}, 42, str(tmp_path / "out"))
    package = json.loads((tmp_path / "out" / "report_package.json").read_text(encoding="utf-8"))
    assert package["render"]["status"] == "failed"
    assert "render boom" in package["render"]["error"]
    assert result["metrics"]["overallScore"] is not None


def test_blocked_without_results(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(str(tmp_path), {}, 42, str(tmp_path / "out"))
    assert result["blockedReason"] == "OPERATOR_RESULTS_REQUIRED"
    assert result["metrics"]["blockedReason"] == "OPERATOR_RESULTS_REQUIRED"
