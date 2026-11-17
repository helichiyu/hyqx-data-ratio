"""OP-16 配比分析与建议（``ratio_analysis_recommend_v1``）。

消费 OP-15 方案表（含每标签×来源有效条数）与基线树：
- 六维能力分与逐标签贡献（FGW 12.1 六类来源→能力映射，Q-05 未提供时为可解释默认映射）；
- 领域相对占比与未覆盖清单；
- 约束下的建议配比、改动量、目标达成度；
- 按真实库存的补数 TopN 与补齐后能力预测；
- 来源/领域偏见指标与通用/专业多方案对标矩阵。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .utils import capability as capability_util
from .utils import mapping as mapping_util
from .utils import recommend as recommend_util
from .utils.common import (
    ensure_output_dir,
    ensure_under_roots,
    environment_roots,
    fingerprint_file,
    fingerprint_path,
    load_config,
    now_iso,
    params_hash,
    resolve_relative,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-ratio-analysis"
SEMANTIC_CODE = "ratio_analysis_recommend_v1"
OPERATOR_VERSION = "0.1.2"
DEFAULT_SEED = 42


def run(
    input_path: str,
    params: dict | None = None,
    seed: int | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    started = time.time()
    cfg = load_config()
    resolved = dict(params or {})
    resolved_seed = DEFAULT_SEED if seed is None else int(seed)
    output = ensure_output_dir(output_dir)
    _clean_output(output)
    input_fingerprint = fingerprint_path(input_path)

    plan_path, rows, plan_meta = _load_plan(input_path, resolved.get("plan_path"))
    target_total = int(
        resolved.get("target_total")
        or plan_meta.get("targetTotal")
        or cfg["targets"]["defaultTargetTotal"]
    )

    if not rows:
        return _blocked(
            output, input_fingerprint, plan_path, "PLAN_ROWS_EMPTY", "OP-15 方案表为空，无法分析配比", cfg, resolved_seed, resolved
        )
    if len(rows) > int(cfg["limits"]["maxLabels"]):
        return _blocked(
            output,
            input_fingerprint,
            plan_path,
            "LABEL_LIMIT_EXCEEDED",
            f"标签数 {len(rows)} 超过上限 {cfg['limits']['maxLabels']}",
            cfg,
            resolved_seed,
            resolved,
        )
    if len(rows) * float(cfg["constraints"]["minLabelShare"]) > 1.0:
        return _blocked(
            output,
            input_fingerprint,
            plan_path,
            "MIN_SHARE_INFEASIBLE",
            "标签数 × 最小占比 > 100%，约束不可行；请提高 minLabelShare 或减少标签数",
            cfg,
            resolved_seed,
            resolved,
        )
    if target_total <= 0:
        return _blocked(
            output,
            input_fingerprint,
            plan_path,
            "INVALID_TARGET_TOTAL",
            f"目标总量必须大于 0，实际 {target_total}",
            cfg,
            resolved_seed,
            resolved,
        )

    current_shares = [float(row.get("share") or 0.0) for row in rows]
    share_total = sum(current_shares)
    if share_total <= 0:
        return _blocked(
            output, input_fingerprint, plan_path, "NO_EFFECTIVE_INVENTORY", "方案表占比合计为 0，无法计算能力与建议", cfg, resolved_seed, resolved
        )
    if abs(share_total - 1.0) > 1e-6:
        return _blocked(
            output,
            input_fingerprint,
            plan_path,
            "PLAN_SHARES_INVALID",
            f"方案表占比合计 {share_total:.10f} 不等于 1，拒绝在未归一化输入上出建议",
            cfg,
            resolved_seed,
            resolved,
        )

    missing_source = [
        row["label"] for row in rows if int(row.get("count") or 0) > 0 and not row.get("bySource")
    ]
    if missing_source:
        return _blocked(
            output,
            input_fingerprint,
            plan_path,
            "PLAN_SOURCE_BREAKDOWN_MISSING",
            "OP-15 方案表缺少每标签×来源拆分（需 OP-15 ≥0.1.1），无法按 FGW 来源→能力映射计算",
            cfg,
            resolved_seed,
            resolved,
            detail={"labels": missing_source[:20], "count": len(missing_source)},
        )

    dimensions = cfg["capability"]["dimensions"]
    keys = [str(item["key"]) for item in dimensions]
    source_weights = cfg["capability"]["sourceWeights"]
    tree = mapping_util.load_tree(resolve_relative(cfg["tree"]["relativePath"]))
    matrix = mapping_util.capability_matrix(rows, dimensions, source_weights)

    capability_current, contributions = capability_util.score(matrix, dimensions, current_shares)
    domain_current = mapping_util.domain_shares(rows, tree, current_shares)
    source_current = mapping_util.source_shares(rows, current_shares)
    sources_for_bias = [source for source in cfg["capability"]["sources"] if source != "unknown"]
    domain_distribution = {
        category: float(domain_current["level1Shares"].get(category, 0.0))
        for category in tree["level1"]
    }
    bias = capability_util.bias_report(source_current, domain_distribution, sources_for_bias, cfg)

    target, target_source, orientation = _resolve_target(resolved, cfg)
    achievement_current = capability_util.achievement(capability_current, target)

    scenarios: list[dict[str, Any]] = [
        {
            "name": "current",
            "description": "OP-15 当前方案",
            "shares": current_shares,
            "capability": capability_current,
            "sourceShares": source_current,
            "generalShare": _group_share(source_current, cfg["benchmark"]["generalSources"]),
            "professionalShare": _group_share(source_current, cfg["benchmark"]["professionalSources"]),
            "level1Coverage": domain_current["level1Coverage"],
            "level2Coverage": domain_current["level2Coverage"],
            "changeL1": 0.0,
        }
    ]
    optimizations: dict[str, Any] = {}
    for name, profile in cfg["targets"]["profiles"].items():
        optimization = recommend_util.optimize(
            current_shares, matrix, profile, dimensions, cfg["objectiveWeights"], cfg["constraints"]
        )
        cap_rec, _ = capability_util.score(matrix, dimensions, optimization["shares"])
        source_rec = mapping_util.source_shares(rows, optimization["shares"])
        domain_rec = mapping_util.domain_shares(rows, tree, optimization["shares"])
        scenarios.append(
            {
                "name": name,
                "description": {
                    "balanced": "均衡目标（六维等权）",
                    "general": "通用/基座目标（语言、知识、推理、对话优先）",
                    "professional": "行业/专业目标（专业深度、推理、编码优先）",
                }.get(name, name),
                "shares": optimization["shares"],
                "capability": cap_rec,
                "sourceShares": source_rec,
                "generalShare": _group_share(source_rec, cfg["benchmark"]["generalSources"]),
                "professionalShare": _group_share(source_rec, cfg["benchmark"]["professionalSources"]),
                "level1Coverage": domain_rec["level1Coverage"],
                "level2Coverage": domain_rec["level2Coverage"],
                "changeL1": optimization["changeL1"],
            }
        )
        optimizations[name] = optimization

    if orientation == "custom":
        custom = recommend_util.optimize(
            current_shares, matrix, target, dimensions, cfg["objectiveWeights"], cfg["constraints"]
        )
        cap_rec, _ = capability_util.score(matrix, dimensions, custom["shares"])
        source_rec = mapping_util.source_shares(rows, custom["shares"])
        domain_rec = mapping_util.domain_shares(rows, tree, custom["shares"])
        scenarios.append(
            {
                "name": "custom",
                "description": "调用方传入的目标能力",
                "shares": custom["shares"],
                "capability": cap_rec,
                "sourceShares": source_rec,
                "generalShare": _group_share(source_rec, cfg["benchmark"]["generalSources"]),
                "professionalShare": _group_share(source_rec, cfg["benchmark"]["professionalSources"]),
                "level1Coverage": domain_rec["level1Coverage"],
                "level2Coverage": domain_rec["level2Coverage"],
                "changeL1": custom["changeL1"],
            }
        )
        optimizations["custom"] = custom

    selected = next(scenario for scenario in scenarios if scenario["name"] == orientation)
    selected_optimization = optimizations[orientation]
    recommended_shares = list(selected["shares"])
    capability_recommended = selected["capability"]
    achievement_recommended = capability_util.achievement(capability_recommended, target)
    constraints = recommend_util.check_constraints(
        recommended_shares, current_shares, cfg["constraints"], orientation
    )

    benchmark_profiles = dict(cfg["targets"]["profiles"])
    if orientation == "custom":
        benchmark_profiles["custom"] = target
    benchmark = recommend_util.benchmark(
        scenarios,
        benchmark_profiles,
        orientation,
        float(cfg["capability"]["scaleMax"]),
    )

    topup = recommend_util.top_up(
        rows,
        recommended_shares,
        target_total,
        capability_current,
        target,
        source_weights,
        dimensions,
        cfg,
    )
    topup["uncoveredLevel1"] = domain_current["uncoveredLevel1"]
    topup["uncoveredLevel2"] = domain_current["uncoveredLevel2"]
    topup["uncoveredCounts"] = {
        "level1": len(domain_current["uncoveredLevel1"]),
        "level2": len(domain_current["uncoveredLevel2"]),
        "note": "未覆盖类别无库存，补数建议只对已有标签按真实库存缺口给出；未覆盖类别需平台连接器补采。",
    }
    sources_by_label = {
        item["label"]: item.get("recommendedSources") or [] for item in topup.get("items") or []
    }

    result_rows: list[dict[str, Any]] = []
    for index, (row, current, recommended) in enumerate(
        zip(rows, current_shares, recommended_shares)
    ):
        feed_current = int(round(current * target_total))
        feed_recommended = int(round(recommended * target_total))
        inventory = int(row.get("count") or 0)
        result_rows.append(
            {
                "label": row["label"],
                "level1": row.get("level1"),
                "level2": row.get("level2"),
                "inventory": inventory,
                "currentShare": round(current, 10),
                "recommendedShare": round(recommended, 10),
                "delta": round(recommended - current, 10),
                "currentFeedCount": feed_current,
                "recommendedFeedCount": feed_recommended,
                "gap": max(0, feed_recommended - inventory),
                "recommendedSources": sources_by_label.get(row["label"], []),
                "capabilityContribution": {
                    key: round(contributions[index][key], 12) for key in keys
                },
            }
        )

    improvements = sorted(result_rows, key=lambda item: (-item["delta"], item["label"]))
    reductions = sorted(result_rows, key=lambda item: (item["delta"], item["label"]))
    objective_drop = selected_optimization["objectiveInitial"] - selected_optimization["objectiveFinal"]
    achievement_gain = (
        achievement_recommended["overall"] - achievement_current["overall"]
        if achievement_recommended["overall"] is not None and achievement_current["overall"] is not None
        else None
    )

    recommendation = {
        "orientation": orientation,
        "targetSource": target_source,
        "target": {key: round(float(target[key]), 10) for key in keys},
        "targetProfiles": cfg["targets"]["profiles"],
        "optimization": {
            "iterations": selected_optimization["iterations"],
            "converged": selected_optimization["converged"],
            "objectiveInitial": selected_optimization["objectiveInitial"],
            "objectiveFinal": selected_optimization["objectiveFinal"],
            "objectiveDrop": round(objective_drop, 12),
            "changeL1": selected_optimization["changeL1"],
            "changeClipped": selected_optimization["changeClipped"],
            "reverted": selected_optimization["reverted"],
        },
        "constraints": constraints,
        "achievement": {
            "current": achievement_current,
            "recommended": achievement_recommended,
            "gain": round(achievement_gain, 10) if achievement_gain is not None else None,
        },
        "topIncreases": [
            {"label": item["label"], "delta": item["delta"], "recommendedShare": item["recommendedShare"]}
            for item in improvements[:10]
        ],
        "topDecreases": [
            {"label": item["label"], "delta": item["delta"], "recommendedShare": item["recommendedShare"]}
            for item in reductions[:10]
        ],
        "definition": (
            "目标：min Σ_dim objectiveWeights·max(0, target-achieved)，约束为合计 100%、"
            "单标签占比 ≥ minLabelShare、总改动 ≤ maxTotalChangeL1；求解为确定性 Frank-Wolfe"
            "（供体→受体转移 + 三分线搜索），结果用最大余数法取整。"
        ),
    }

    capability_report = {
        "dimensions": dimensions,
        "mapping": {
            "version": cfg["version"],
            "status": cfg["status"],
            "statusNote": cfg["statusNote"],
            "sourceWeights": source_weights,
            "note": "FGW 12.1 六类来源→能力映射；Q-05 权威映射库未提供，按可解释默认映射执行并标 provisional",
        },
        "current": {
            "vector": {key: round(capability_current[key], 10) for key in keys},
            "score10": {
                key: round(capability_current[key] * float(cfg["capability"]["scaleMax"]), 4)
                for key in keys
            },
            "contributions": [
                {"label": row["label"], **{key: round(contributions[index][key], 12) for key in keys}}
                for index, row in enumerate(rows)
            ],
        },
        "recommended": {
            "vector": {key: round(capability_recommended[key], 10) for key in keys},
            "score10": {
                key: round(capability_recommended[key] * float(cfg["capability"]["scaleMax"]), 4)
                for key in keys
            },
        },
        "achievement": {"current": achievement_current, "recommended": achievement_recommended},
        "domain": domain_current,
        "bias": bias,
        "definition": "能力分 = Σ_label 占比 × 标签能力向量；贡献度逐标签可加总回能力分；能力向量合计 1",
    }

    run_id = _run_id(input_fingerprint, resolved, resolved_seed)
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "capability": {
            "current": {key: round(capability_current[key], 10) for key in keys},
            "recommended": {key: round(capability_recommended[key], 10) for key in keys},
            "currentScore10": {
                key: round(capability_current[key] * float(cfg["capability"]["scaleMax"]), 4)
                for key in keys
            },
            "recommendedScore10": {
                key: round(capability_recommended[key] * float(cfg["capability"]["scaleMax"]), 4)
                for key in keys
            },
        },
        "achievement": {
            "currentOverall": achievement_current["overall"],
            "recommendedOverall": achievement_recommended["overall"],
            "gain": round(achievement_gain, 10) if achievement_gain is not None else None,
        },
        "recommendation": {
            "orientation": orientation,
            "targetSource": target_source,
            "iterations": selected_optimization["iterations"],
            "converged": selected_optimization["converged"],
            "objectiveInitial": selected_optimization["objectiveInitial"],
            "objectiveFinal": selected_optimization["objectiveFinal"],
            "changeL1": selected_optimization["changeL1"],
            "changeClipped": selected_optimization["changeClipped"],
            "reverted": selected_optimization["reverted"],
            "constraintsPassed": constraints["allPassed"],
            "checks": constraints["checks"],
        },
        "bias": {
            "source": {
                key: bias["source"][key]
                for key in ("gini", "hhi", "normalizedEntropy", "topShare", "biasLevel", "unknownShare")
            },
            "domain": {
                key: bias["domain"][key]
                for key in ("gini", "hhi", "normalizedEntropy", "topShare", "biasLevel", "categoryCount")
            },
        },
        "domain": {
            "level1Coverage": domain_current["level1Coverage"],
            "level2Coverage": domain_current["level2Coverage"],
            "uncoveredLevel1Count": len(domain_current["uncoveredLevel1"]),
            "uncoveredLevel2Count": len(domain_current["uncoveredLevel2"]),
            "level1Shares": domain_current["level1Shares"],
        },
        "topUp": {
            "totalGap": topup["totalGap"],
            "gapLabelCount": topup["gapLabelCount"],
            "sourceTotals": topup["sourceTotals"],
            "uncoveredLevel1Count": topup["uncoveredCounts"]["level1"],
            "uncoveredLevel2Count": topup["uncoveredCounts"]["level2"],
            "predictedOverall": capability_util.achievement(topup["predictedCapability"], target)["overall"],
        },
        "benchmark": {
            "orientation": orientation,
            "recommendedScenario": benchmark["recommendedScenario"],
            "achievements": {row["scenario"]: row["achievement"] for row in benchmark["rows"]},
        },
        "mappingVersion": cfg["version"],
        "mappingStatus": cfg["status"],
        "treeVersion": tree["treeVersion"],
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }

    result_path = output / "result.jsonl"
    capability_path = output / "capability.json"
    recommendation_path = output / "recommendation.json"
    topup_path = output / "topup.json"
    benchmark_path = output / "benchmark.json"
    metrics_path = output / "metrics.json"
    input_manifest_path = output / "input_manifest.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, result_rows)
    write_json(capability_path, capability_report)
    write_json(recommendation_path, recommendation)
    write_json(topup_path, topup)
    write_json(benchmark_path, {**benchmark, "targetProfiles": cfg["targets"]["profiles"]})
    write_json(metrics_path, metrics)

    plan_fingerprint, plan_bytes = fingerprint_file(plan_path)
    write_json(
        input_manifest_path,
        {
            "planPath": plan_path.as_posix(),
            "planFingerprint": f"sha256:{plan_fingerprint}",
            "inputFingerprint": f"sha256:{input_fingerprint}",
            "planBytes": plan_bytes,
            "labelCount": len(rows),
            "targetTotal": target_total,
            "treeVersion": tree["treeVersion"],
            "mappingVersion": cfg["version"],
            "mappingStatus": cfg["status"],
            "note": "能力映射来自 FGW 12.1 可解释默认映射；Q-05 权威库到位后按版本替换。",
        },
    )

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    output_bytes = sum(item["bytes"] for item in artifacts)
    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": tree["treeVersion"],
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": len(rows),
        "successCount": len(rows),
        "failedCount": 0,
        "inputBytes": plan_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / plan_bytes, 6) if plan_bytes else 0.0,
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "notes": [
            "能力映射 = FGW 12.1 六类来源→能力可解释默认映射（Q-05 权威库待提供），结果标 provisional。",
            "建议配比在合计 100%、标签上下限与总改动上限约束下用确定性 Frank-Wolfe 求解，取整用最大余数法。",
            "补数按真实库存缺口计算；目标能力模板为 FGW 12.4-4 应用导向联调初值。",
            "不编造人工标注/专家真值；效果类指标不在此算子计算。",
        ],
    }
    write_json(manifest_path, manifest)

    write_json(
        summary_path,
        {
            "operatorId": OPERATOR_ID,
            "semanticCode": SEMANTIC_CODE,
            "operatorVersion": OPERATOR_VERSION,
            "runId": run_id,
            "inputFingerprint": manifest["inputFingerprint"],
            "paramsHash": manifest["paramsHash"],
            "seed": resolved_seed,
            "modelVersion": None,
            "treeVersion": tree["treeVersion"],
            "sampleCount": len(rows),
            "successCount": len(rows),
            "failedCount": 0,
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )

    return {
        "modelVersion": None,
        "treeVersion": tree["treeVersion"],
        "sampleCount": len(rows),
        "successCount": len(rows),
        "failedCount": 0,
        "failedSamples": [],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "result": {
            "capability": capability_report["current"],
            "achievement": recommendation["achievement"],
            "recommendation": {
                "orientation": orientation,
                "target": recommendation["target"],
                "constraints": constraints,
                "topIncreases": recommendation["topIncreases"],
                "topDecreases": recommendation["topDecreases"],
            },
            "topUp": {
                "totalGap": topup["totalGap"],
                "gapLabelCount": topup["gapLabelCount"],
                "topN": topup["topN"],
                "sourceTotals": topup["sourceTotals"],
            },
            "benchmark": benchmark["rows"],
        },
        "notes": [
            "六维能力分/贡献度见 capability.json；建议配比见 recommendation.json；补数见 topup.json；对标见 benchmark.json。",
            "映射库与目标能力模板待业务确认（Q-05/H-12），结果标 provisional。",
        ],
    }


def _resolve_target(
    params: dict[str, Any], cfg: dict[str, Any]
) -> tuple[dict[str, float], str, str]:
    raw = params.get("target_capability")
    keys = [str(item["key"]) for item in cfg["capability"]["dimensions"]]
    if isinstance(raw, dict):
        missing = [key for key in keys if key not in raw]
        if missing:
            raise ValueError(f"target_capability 缺少维度：{missing}")
        values = {key: float(raw[key]) for key in keys}
        if any(value < 0 for value in values.values()):
            raise ValueError("target_capability 不允许负值")
        total = sum(values.values())
        if total <= 0:
            raise ValueError("target_capability 合计必须大于 0")
        return {key: value / total for key, value in values.items()}, "params", "custom"
    orientation = str(params.get("orientation") or cfg["targets"]["defaultOrientation"])
    profiles = cfg["targets"]["profiles"]
    if orientation not in profiles:
        raise ValueError(f"orientation 必须是 {sorted(profiles)} 之一，实际 {orientation}")
    return dict(profiles[orientation]), f"config:profile:{orientation}", orientation


def _group_share(source_shares: dict[str, float], group: list[str]) -> float:
    return sum(float(source_shares.get(source, 0.0)) for source in group)


def _load_plan(
    input_path: str, raw_plan: Any
) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    if raw_plan:
        path = ensure_under_roots(str(raw_plan), environment_roots())
    else:
        path = Path(input_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"输入不存在：{path}")
    if path.is_dir():
        candidate = path / "plan.json"
        if candidate.is_file():
            path = candidate
        else:
            candidate = path / "result.jsonl"
            if not candidate.is_file():
                raise FileNotFoundError(f"目录中没有 plan.json 或 result.jsonl：{path}")
            path = candidate
    if path.suffix.lower() == ".jsonl":
        rows = _read_jsonl(path)
        return path, rows, {"targetTotal": None}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"plan.json 缺少非空 rows：{path}")
    target_total = (payload.get("normalization") or {}).get("targetTotal")
    return path, [dict(row) for row in rows], {"targetTotal": target_total}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict) and "label" in payload:
                rows.append(payload)
    return rows


def _blocked(
    output: Path,
    input_fingerprint: str,
    plan_path: Path,
    reason: str,
    message: str,
    cfg: dict[str, Any],
    seed: int,
    params: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """输入不足以计算结果时如实返回 blocked，不伪造能力分/建议。"""

    write_jsonl(output / "result.jsonl", [])
    plan_fingerprint, plan_bytes = (
        fingerprint_file(plan_path) if plan_path.is_file() else (hashlib.sha256(b"missing").hexdigest(), 0)
    )
    run_id = _run_id(input_fingerprint, params, seed)
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(params)}",
        "seed": seed,
        "treeVersion": None,
        "blockedReason": reason,
        "message": message,
        "detail": detail or {},
        "provisional": True,
        "deterministic": True,
        "mappingVersion": cfg["version"],
        "mappingStatus": cfg["status"],
        "generatedAt": now_iso(),
    }
    write_json(output / "metrics.json", metrics)
    write_json(
        output / "input_manifest.json",
        {
            "planPath": plan_path.as_posix(),
            "planFingerprint": f"sha256:{plan_fingerprint}",
            "inputFingerprint": f"sha256:{input_fingerprint}",
            "planBytes": plan_bytes,
            "note": message,
        },
    )
    artifacts = _collect_artifacts(
        output, exclude={"manifest.json", "summary.json", "result.json", "error.log"}
    )
    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(params)}",
        "seed": seed,
        "sampleCount": 0,
        "successCount": 0,
        "failedCount": 0,
        "inputBytes": plan_bytes,
        "outputBytes": sum(item["bytes"] for item in artifacts),
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "blockedReason": reason,
    }
    write_json(output / "manifest.json", manifest)
    write_json(
        output / "summary.json",
        {
            "operatorId": OPERATOR_ID,
            "semanticCode": SEMANTIC_CODE,
            "operatorVersion": OPERATOR_VERSION,
            "runId": run_id,
            "inputFingerprint": manifest["inputFingerprint"],
            "paramsHash": manifest["paramsHash"],
            "seed": seed,
            "treeVersion": None,
            "sampleCount": 0,
            "successCount": 0,
            "failedCount": 0,
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )
    return {
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": 0,
        "successCount": 0,
        "failedCount": 0,
        "failedSamples": [],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": (output / "result.jsonl").as_posix(),
        "deterministic": True,
        "provisional": True,
        "blockedReason": reason,
        "notes": [message, "未做任何能力分/建议推算，不伪造结果。"],
    }


def _clean_output(output: Path) -> None:
    for name in (
        "result.jsonl",
        "capability.json",
        "recommendation.json",
        "topup.json",
        "benchmark.json",
        "metrics.json",
        "manifest.json",
        "summary.json",
        "input_manifest.json",
    ):
        (output / name).unlink(missing_ok=True)


def _collect_artifacts(output: Path, exclude: set[str]) -> list[dict[str, Any]]:
    items = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name in exclude:
            continue
        items.append(
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return items


def _run_id(fingerprint: str, params: dict[str, Any], seed: int) -> str:
    return hashlib.sha256(
        f"{fingerprint}|{OPERATOR_VERSION}|{params_hash(params)}|{seed}".encode("utf-8")
    ).hexdigest()[:16]
