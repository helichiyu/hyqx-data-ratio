"""从各算子 ``metrics.json`` 提取九维真实指标；缺数据标 no_data，不编造。"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def load_metrics(results: dict[str, str | Path]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    metrics: dict[str, dict[str, Any]] = {}
    problems: dict[str, str] = {}
    for op_id, raw_path in results.items():
        path = Path(raw_path)
        candidate = path / "metrics.json" if path.is_dir() else path
        if not candidate.is_file():
            problems[op_id] = f"metrics.json 不存在：{candidate}"
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems[op_id] = f"metrics.json 不可解析：{exc}"
            continue
        if not isinstance(payload, dict):
            problems[op_id] = "metrics.json 不是对象"
            continue
        metrics[op_id] = payload
    return metrics, problems


def _get(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _entropy(shares: list[float]) -> float | None:
    total = sum(shares)
    if total <= 0 or len(shares) <= 1:
        return None
    entropy = -sum((value / total) * math.log(value / total) for value in shares if value > 0)
    return entropy / math.log(len(shares))


def _ok(score: float | None, raw: dict[str, Any], method: str) -> dict[str, Any]:
    if score is None:
        return {"score": None, "status": "no_data", "reason": "指标缺失或非数值", "raw": raw, "method": method}
    return {"score": round(max(0.0, min(1.0, float(score))), 10), "status": "ok", "reason": None, "raw": raw, "method": method}


def _scale_source(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = metrics.get("OP-08") or {}
    classes = _get(payload, "sourceDistribution.classes")
    if not isinstance(classes, dict) or not classes:
        return _ok(None, {}, "六类来源占比的归一化熵（log 6）")
    shares = []
    for item in classes.values():
        if isinstance(item, dict):
            share = _number(item.get("sharePercent"))
            if share is not None:
                shares.append(share / 100.0)
    raw = {
        "classes": {
            key: {
                "count": item.get("count"),
                "sharePercent": item.get("sharePercent"),
            }
            for key, item in classes.items()
            if isinstance(item, dict)
        },
        "recordCount": _get(payload, "scale.recordCount"),
        "shareSumPercent": _get(payload, "sourceDistribution.shareSumPercent"),
    }
    return _ok(_entropy(shares), raw, "六类来源占比的归一化熵（log 6）")


def _domain_coverage(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = metrics.get("OP-08") or {}
    coverage = _get(payload, "domainCoverage.coverage.level1")
    raw = {
        "level1": coverage,
        "level2": _get(payload, "domainCoverage.coverage.level2"),
        "leaf": _get(payload, "domainCoverage.coverage.leaf"),
        "gaps": _get(payload, "domainCoverage.gaps"),
    }
    return _ok(_number(coverage), raw, "内容树一级类别覆盖率")


def _language_time(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = metrics.get("OP-09") or {}
    freshness = _number(_get(payload, "time.freshnessMean"))
    raw = {
        "freshnessMean": freshness,
        "knownTimeRatio": _get(payload, "time.knownTimeRatio"),
        "staleShare": _get(payload, "time.staleShare"),
        "languageStatus": _get(payload, "language.statusCounts"),
        "regionStatus": _get(payload, "region.status"),
    }
    return _ok(freshness, raw, "新鲜度指数（FGW 公式）；地域不可用单列")


def _text_taskfit(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = metrics.get("OP-10") or {}
    p50 = _number(_get(payload, "distributions.overall.p50"))
    raw = {
        "overallP50": p50,
        "overallP90": _get(payload, "distributions.overall.p90"),
        "lowFitCount": _get(payload, "lowFitCount"),
        "evaluatedRecords": _get(payload, "evaluatedRecords"),
    }
    return _ok(p50 / 10.0 if p50 is not None else None, raw, "六维任务适配总分 p50（0–10）归一化")


def _quality_consistency(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = metrics.get("OP-14") or {}
    completeness = _number(_get(payload, "completeness.mean"))
    gini = _number(_get(payload, "gini.gini"))
    balance = _number(_get(payload, "polarity.balance"))
    values = [value for value in (completeness, 1.0 - gini if gini is not None else None, balance) if value is not None]
    raw = {
        "completenessMean": completeness,
        "gini": gini,
        "polarityBalance": balance,
        "nearDuplicateGroups": _get(payload, "conflict.nearDuplicateGroups"),
        "conflictRate": _get(payload, "conflict.conflictRate"),
    }
    return _ok(sum(values) / len(values) if values else None, raw, "完整率、1−基尼、极性平衡度三者均值")


def _label_legality(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    op05 = metrics.get("OP-05") or {}
    op07 = metrics.get("OP-07") or {}
    path_legal = _number(_get(op05, "pathLegalRate"))
    legal = _number(_get(op07, "legalRate"))
    values = [value for value in (path_legal, legal) if value is not None]
    raw = {
        "pathLegalRate": path_legal,
        "legalRate": legal,
        "labeledRate": _get(op05, "labeledRate"),
        "unclassifiedRecords": _get(op07, "unclassifiedRecords"),
        "illegalLabels": _get(op07, "illegalLabels"),
    }
    return _ok(sum(values) / len(values) if values else None, raw, "OP-05 路径合法率与 OP-07 合法率均值；标注覆盖率单列")


def _ratio_compliance(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = metrics.get("OP-15") or {}
    passed = _number(_get(payload, "checksPassed"))
    total = _number(_get(payload, "checksTotal"))
    score = passed / total if passed is not None and total else None
    raw = {
        "checksPassed": passed,
        "checksTotal": total,
        "failedChecks": _get(payload, "failedChecks"),
        "shareSum": payload.get("shareSum"),
        "coreCoverage": next(
            (
                item.get("actual")
                for item in payload.get("checks") or []
                if isinstance(item, dict) and item.get("id") == "core_label_coverage"
            ),
            None,
        ),
    }
    return _ok(score, raw, "OP-15 校验单通过比例（6 项）")


def _assembly_integrity(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = metrics.get("OP-17") or {}
    duplicate = _number(_get(payload, "duplicateRecords"))
    rows = _number(_get(payload, "dataset.rows"))
    selected = _number(payload.get("selectedCount"))
    if duplicate is None or rows is None or selected is None:
        score = None
    else:
        mismatch = abs(rows - selected) / max(selected, 1.0)
        score = 0.0 if duplicate > 0 else max(0.0, 1.0 - mismatch)
    raw = {
        "duplicateRecords": duplicate,
        "datasetRows": rows,
        "selectedCount": selected,
        "selectionRate": payload.get("selectionRate"),
        "inventoryGap": payload.get("inventoryGap"),
    }
    return _ok(score, raw, "无重复且 Parquet 行数=选样数记 1，否则按差异比例扣减")


def _evaluation_quality(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = metrics.get("OP-18") or {}
    score = _number(_get(payload, "score.score"))
    truth = _get(payload, "truth") or {}
    raw = {
        "score": score,
        "grade": _get(payload, "score.grade"),
        "scoreScope": _get(payload, "score.scope"),
        "truthStatus": truth.get("status") if isinstance(truth, dict) else None,
        "truthBlockedReason": truth.get("blockedReason") if isinstance(truth, dict) else None,
        "pathLegalityRate": _get(payload, "proxy.pathLegalityRate"),
        "complianceStatus": _get(payload, "compliance.status"),
    }
    return _ok(score, raw, "OP-18 综合质量分（可用分项加权；真值缺失时仍需标 proxy）")


EXTRACTORS = {
    "scale_source": _scale_source,
    "domain_coverage": _domain_coverage,
    "language_time": _language_time,
    "text_taskfit": _text_taskfit,
    "quality_consistency": _quality_consistency,
    "label_legality": _label_legality,
    "ratio_compliance": _ratio_compliance,
    "assembly_integrity": _assembly_integrity,
    "evaluation_quality": _evaluation_quality,
}


def collect(metrics: dict[str, dict[str, Any]], cfg: dict[str, Any], problems: dict[str, str]) -> list[dict[str, Any]]:
    dimensions = []
    for definition in cfg["dimensions"]:
        key = str(definition["key"])
        extractor = EXTRACTORS.get(key)
        result = extractor(metrics) if extractor else {"score": None, "status": "no_data", "reason": "未知维度"}
        score = result.get("score")
        thresholds = definition["thresholds"]
        if score is None:
            grade = "no_data"
        elif score >= float(thresholds["excellent"]):
            grade = "excellent"
        elif score >= float(thresholds["good"]):
            grade = "good"
        elif score >= float(thresholds["pass"]):
            grade = "pass"
        else:
            grade = "fail"
        dimensions.append(
            {
                "key": key,
                "nameZh": definition["nameZh"],
                "operator": definition["operator"],
                "metric": definition["metric"],
                "weight": float(definition["weight"]),
                "method": result.get("method") or definition.get("method"),
                "score": score,
                "grade": grade,
                "status": result.get("status"),
                "reason": result.get("reason") or problems.get(str(definition["operator"]).split("/")[0]),
                "raw": result.get("raw"),
                "thresholds": thresholds,
            }
        )
    return dimensions
