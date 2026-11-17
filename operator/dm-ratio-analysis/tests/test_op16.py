"""OP-16 单测与端到端：能力贡献、达成度、约束建议、补数、偏见、幂等与真实批次。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from op16_env import CORE, latest_op15_evidence

cfg = CORE.load_config()
capability = CORE.capability_util
mapping = CORE.mapping_util
recommend = CORE.recommend_util
DIMS = cfg["capability"]["dimensions"]
KEYS = [item["key"] for item in DIMS]
SOURCE_WEIGHTS = cfg["capability"]["sourceWeights"]


def _row(label: str, share: float, count: int, by_source: dict[str, int]) -> dict:
    return {
        "label": label,
        "level1": label.split("/")[0],
        "level2": "/".join(label.split("/")[:2]),
        "count": count,
        "share": share,
        "effectiveCount": float(count),
        "bySource": {
            source: {"count": value, "effectiveCount": float(value)}
            for source, value in by_source.items()
        },
    }


def _rows() -> list[dict]:
    return [
        _row("新闻与资讯/科技新闻/产品发布与行业动态", 0.5, 50, {"web_text": 50}),
        _row("代码与技术文档/程序代码/各语言源代码与脚本", 0.3, 30, {"code": 30}),
        _row("对话与交互/指令与训练/RLHF数据", 0.2, 20, {"dialogue": 20}),
    ]


def _plan(tmp_path: Path, rows: list[dict], target_total: int = 100) -> Path:
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "rows": rows,
        "normalization": {"targetTotal": target_total},
    }
    (plan_dir / "plan.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return plan_dir


def test_source_mapping_rows_sum_to_one():
    for source in SOURCE_WEIGHTS:
        assert abs(sum(SOURCE_WEIGHTS[source].values()) - 1.0) < 1e-9, source


def test_capability_contributions_sum():
    rows = _rows()
    matrix = mapping.capability_matrix(rows, DIMS, SOURCE_WEIGHTS)
    vector, contributions = capability.score(matrix, DIMS, [row["share"] for row in rows])
    for key in KEYS:
        assert abs(sum(item[key] for item in contributions) - vector[key]) < 1e-12
    assert abs(sum(vector.values()) - 1.0) < 1e-9


def test_achievement_definition():
    report = capability.achievement(
        {"language": 0.3, "coding": 0.1},
        {"language": 0.4, "coding": 0.2},
    )
    assert report["overall"] == pytest.approx(0.4 / 0.6)
    assert report["l1Distance"] == pytest.approx(0.2)
    assert report["dimensions"]["language"]["ratio"] == pytest.approx(0.75)


def test_domain_shares_rollup():
    rows = _rows()
    tree = mapping.load_tree(CORE.resolve_relative(cfg["tree"]["relativePath"]))
    report = mapping.domain_shares(rows, tree)
    assert report["level1Shares"]["新闻与资讯"] == pytest.approx(0.5)
    assert report["level1Shares"]["代码与技术文档"] == pytest.approx(0.3)
    assert "新闻与资讯" not in report["uncoveredLevel1"]
    assert report["level1Coverage"] == pytest.approx(3 / len(tree["level1"]))


def test_quantize_sums_to_one_and_min_share():
    shares = recommend.quantize([0.9999, 0.0001, 0.0], 6, 0.0001)
    assert abs(sum(shares) - 1.0) < 1e-12
    assert shares[1] >= 0.0001
    assert shares[2] == 0.0


def test_optimize_constraints_and_improvement():
    rows = _rows()
    matrix = mapping.capability_matrix(rows, DIMS, SOURCE_WEIGHTS)
    current = [row["share"] for row in rows]
    target = cfg["targets"]["profiles"]["professional"]
    result = recommend.optimize(
        current, matrix, target, DIMS, cfg["objectiveWeights"], cfg["constraints"]
    )
    assert abs(sum(result["shares"]) - 1.0) < 1e-9
    assert all(
        cfg["constraints"]["minLabelShare"] <= value <= cfg["constraints"]["maxLabelShare"]
        for value in result["shares"]
    )
    assert result["changeL1"] <= cfg["constraints"]["maxTotalChangeL1"] + 1e-9
    assert result["objectiveFinal"] <= result["objectiveInitial"] + 1e-9
    checks = recommend.check_constraints(result["shares"], current, cfg["constraints"], "professional")
    assert checks["allPassed"] is True


def test_change_clipped_flag_when_budget_binds():
    rows = _rows()
    matrix = mapping.capability_matrix(rows, DIMS, SOURCE_WEIGHTS)
    current = [row["share"] for row in rows]
    constraints = dict(cfg["constraints"])
    constraints["maxTotalChangeL1"] = 0.001
    result = recommend.optimize(
        current,
        matrix,
        cfg["targets"]["profiles"]["professional"],
        DIMS,
        cfg["objectiveWeights"],
        constraints,
    )
    assert result["changeL1"] <= 0.001 + 1e-9
    assert result["changeClipped"] is True


def test_quantize_infeasible_raises():
    with pytest.raises(ValueError):
        recommend.quantize([0.0001] * 10001, 6, 0.0001)


def test_topup_uses_real_inventory():
    rows = _rows()
    recommended = [0.5, 0.5, 0.0]
    result = recommend.top_up(
        rows,
        recommended,
        100,
        {"language": 0.2, "knowledge": 0.1, "reasoning": 0.2, "expertise": 0.1, "coding": 0.3, "dialogue": 0.1},
        cfg["targets"]["profiles"]["balanced"],
        SOURCE_WEIGHTS,
        DIMS,
        cfg,
    )
    labels = {item["label"]: item for item in result["items"]}
    assert labels["新闻与资讯/科技新闻/产品发布与行业动态"]["gap"] == 0
    assert labels["代码与技术文档/程序代码/各语言源代码与脚本"]["gap"] == 20
    assert labels["对话与交互/指令与训练/RLHF数据"]["gap"] == 0
    assert result["totalGap"] == 20
    top = result["topN"][0]
    assert top["gap"] == 20
    assert top["recommendedSources"]
    assert abs(sum(result["predictedCapability"].values()) - 1.0) < 1e-9
    assert sum(result["sourceTotals"].values()) == result["totalGap"]


def test_topup_normalizes_when_feed_rounding_loses_mass():
    rows = [_row("新闻与资讯/科技新闻/产品发布与行业动态", 0.333333, 1, {"web_text": 1}),
            _row("代码与技术文档/程序代码/各语言源代码与脚本", 0.333333, 1, {"code": 1}),
            _row("对话与交互/指令与训练/RLHF数据", 0.333334, 1, {"dialogue": 1})]
    result = recommend.top_up(
        rows,
        [row["share"] for row in rows],
        10,
        {"language": 0.2, "knowledge": 0.2, "reasoning": 0.2, "expertise": 0.2, "coding": 0.1, "dialogue": 0.1},
        cfg["targets"]["profiles"]["balanced"],
        SOURCE_WEIGHTS,
        DIMS,
        cfg,
    )
    assert abs(sum(result["predictedCapability"].values()) - 1.0) < 1e-9
    assert sum(result["sourceTotals"].values()) == result["totalGap"]
    assert result["predictedMass"] <= 1.0


def test_bias_metrics_manual():
    uniform = {source: 1.0 for source in ("web_text", "books", "code", "science", "wiki", "dialogue")}
    report = capability.bias_report(uniform, {"a": 1.0, "b": 1.0}, list(uniform), cfg)
    assert report["source"]["gini"] == pytest.approx(0.0, abs=1e-9)
    assert report["source"]["hhi"] == pytest.approx(1 / 6, abs=1e-9)
    assert report["source"]["normalizedEntropy"] == pytest.approx(1.0, abs=1e-9)

    concentrated = {"web_text": 1.0}
    report = capability.bias_report(concentrated, {"a": 1.0}, list(uniform), cfg)
    assert report["source"]["gini"] == pytest.approx(0.8333333333, abs=1e-6)
    assert report["source"]["hhi"] == pytest.approx(1.0)
    assert report["source"]["normalizedEntropy"] == pytest.approx(0.0)
    assert report["source"]["biasLevel"] == "high"


def test_blocked_without_source_breakdown(tmp_path: Path):
    row = _row("新闻与资讯/科技新闻/产品发布与行业动态", 1.0, 10, {"web_text": 10})
    row.pop("bySource")
    plan_dir = _plan(tmp_path, [row])
    result = CORE.run(str(plan_dir), {}, 42, str(tmp_path / "out"))
    assert result["blockedReason"] == "PLAN_SOURCE_BREAKDOWN_MISSING"
    assert result["metrics"].get("capability") is None


def test_core_end_to_end_and_deterministic(tmp_path: Path):
    plan_dir = _plan(tmp_path, _rows())
    first = CORE.run(str(plan_dir), {"orientation": "professional"}, 42, str(tmp_path / "a"))
    second = CORE.run(str(plan_dir), {"orientation": "professional"}, 42, str(tmp_path / "b"))
    assert first["sampleCount"] == 3
    for field in ("operatorVersion", "modelVersion", "treeVersion", "paramsHash", "seed", "runId"):
        assert field in first["metrics"], field
    assert abs(sum(first["metrics"]["capability"]["current"].values()) - 1.0) < 1e-9
    assert first["metrics"]["recommendation"]["constraintsPassed"] is True
    assert first["metrics"]["recommendation"]["objectiveFinal"] <= (
        first["metrics"]["recommendation"]["objectiveInitial"] + 1e-9
    )
    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()
    for name in ("capability.json", "recommendation.json", "topup.json", "benchmark.json", "metrics.json"):
        assert (tmp_path / "a" / name).is_file(), name


def test_benchmark_recomputable(tmp_path: Path):
    plan_dir = _plan(tmp_path, _rows())
    CORE.run(str(plan_dir), {}, 42, str(tmp_path / "out"))
    benchmark = json.loads((tmp_path / "out" / "benchmark.json").read_text(encoding="utf-8"))
    profiles = benchmark["targetProfiles"]
    for row in benchmark["rows"]:
        for name, profile in profiles.items():
            expected = capability.achievement(row["capability"], profile)["overall"]
            assert row["achievement"][name] == pytest.approx(expected, abs=1e-9)


def test_real_plan_batch(tmp_path: Path):
    evidence = latest_op15_evidence()
    if evidence is None:
        pytest.skip("缺少 OP-15 证据目录")
    plan = json.loads((evidence / "plan.json").read_text(encoding="utf-8"))
    if any(row.get("count") and not row.get("bySource") for row in plan.get("rows") or []):
        pytest.skip("OP-15 方案表为 0.1.0（缺 bySource），请重跑 S4 链路")
    result = CORE.run(str(evidence), {}, 42, str(tmp_path / "real"))
    metrics = result["metrics"]
    assert result["sampleCount"] > 0
    assert abs(sum(metrics["capability"]["current"].values()) - 1.0) < 1e-9
    assert metrics["recommendation"]["constraintsPassed"] is True
    assert metrics["benchmark"]["recommendedScenario"] == "balanced"
