"""OP-22 单测：双阈值、最小样本、去重/抑制、证据、过时状态。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from op22_env import CORE

cfg = CORE.load_config()
rules = CORE.rules_util


def _metrics(**overrides) -> dict:
    base = {
        "OP-08": {"domainCoverage": {"coverage": {"level1": 0.95}}, "scale": {"recordCount": 400}},
        "OP-09": {"time": {"freshnessMean": 0.5}},
        "OP-14": {"gini": {"gini": 0.4, "instanceCount": 300}},
        "OP-15": {"checksPassed": 6, "totalEffective": 300},
        "OP-18": {"population": 300, "truth": {"status": "ok"}, "compliance": {"hitRate": 0.0}},
    }
    for key, value in overrides.items():
        base[key] = value
    return base


def _paths() -> dict[str, str]:
    return {key: f"/tmp/{key}/metrics.json" for key in ("OP-08", "OP-09", "OP-14", "OP-15", "OP-18")}


def test_rule_levels_and_no_hit():
    metrics = _metrics()
    report = rules.evaluate(metrics, {}, cfg, _paths())
    assert report["risks"] == []

    metrics = _metrics(**{"OP-09": {"time": {"freshnessMean": 0.3}}})
    report = rules.evaluate(metrics, {}, cfg, _paths())
    item = report["risks"][0]
    assert item["type"] == "时效过时"
    assert item["level"] == "warning"
    assert item["evidence"]["metricsPath"].endswith("OP-09/metrics.json")

    metrics = _metrics(**{"OP-09": {"time": {"freshnessMean": 0.1}}})
    report = rules.evaluate(metrics, {}, cfg, _paths())
    assert report["risks"][0]["level"] == "critical"


def test_min_sample_blocks_rule():
    metrics = _metrics(**{
        "OP-08": {"domainCoverage": {"coverage": {"level1": 0.5}}, "scale": {"recordCount": 50}},
    })
    report = rules.evaluate(metrics, {}, cfg, _paths())
    assert not any(item["ruleId"] == "R-02" for item in report["risks"])
    assert any(item["ruleId"] == "R-02" for item in report["insufficientSample"])


def test_dedupe_and_suppression():
    custom = copy.deepcopy(cfg)
    custom["rules"] = [
        {"id": "A1", "type": "同一风险", "operator": "OP-09", "metric": "time.freshnessMean", "op": "lt", "warn": 0.4, "critical": 0.2, "minSample": 0},
        {"id": "A2", "type": "同一风险", "operator": "OP-09", "metric": "time.freshnessMean", "op": "lt", "warn": 0.6, "critical": 0.1, "minSample": 0},
    ]
    custom["suppression"] = {"enabled": True, "maxPerType": 1}
    metrics = _metrics(**{"OP-09": {"time": {"freshnessMean": 0.05}}})
    report = rules.evaluate(metrics, {}, custom, _paths())
    assert len(report["risks"]) == 1
    assert report["risks"][0]["level"] == "critical"
    assert report["rawHits"] == 2


def test_outdated_unavailable():
    metrics = _metrics()
    report = rules.evaluate(metrics, {}, cfg, _paths())
    assert report["outdated"]["status"] == "unavailable"
    assert report["outdated"]["reasonCode"] == "KNOWLEDGE_BASE_REQUIRED"


def test_core_evidence_and_blocked(tmp_path: Path, monkeypatch):
    root = tmp_path / "results"
    payload = _metrics(**{"OP-09": {"time": {"freshnessMean": 0.1}}})
    results = {}
    for operator, data in payload.items():
        directory = root / operator
        directory.mkdir(parents=True)
        (directory / "metrics.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        results[operator] = str(directory)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(str(root), {"operator_results": results}, 42, str(tmp_path / "out"))
    assert result["metrics"]["criticalCount"] >= 1
    risks = [json.loads(line) for line in (tmp_path / "out" / "risks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert risks[0]["evidence"]["value"] == 0.1
    assert (tmp_path / "out" / "risk_report.json").is_file()

    blocked = CORE.run(str(tmp_path), {}, 42, str(tmp_path / "blocked"))
    assert blocked["blockedReason"] == "OPERATOR_RESULTS_REQUIRED"
