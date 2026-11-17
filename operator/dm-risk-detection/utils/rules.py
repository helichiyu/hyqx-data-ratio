"""JSON 规则 DSL 求值：双阈值、作用域、最小样本、去重/抑制与证据引用。"""

from __future__ import annotations

from typing import Any


def get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def compare(value: Any, op: str, threshold: Any) -> bool:
    if op in {"eq", "ne"}:
        result = value == threshold
        return result if op == "eq" else not result
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        return False
    if op == "lt":
        return value < threshold
    if op == "gt":
        return value > threshold
    if op == "le":
        return value <= threshold
    if op == "ge":
        return value >= threshold
    return False


def _sample_size(payload: dict[str, Any], operator: str, cfg: dict[str, Any]) -> int | None:
    for path in cfg["samplePaths"].get(operator, []):
        value = get_path(payload, path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return None


def evaluate(
    metrics: dict[str, dict[str, Any]],
    problems: dict[str, str],
    cfg: dict[str, Any],
    evidence_paths: dict[str, str],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    no_data: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []
    evaluated = 0
    severity = cfg["severity"]

    for rule in cfg["rules"]:
        operator = str(rule["operator"])
        payload = metrics.get(operator)
        if payload is None:
            no_data.append({"ruleId": rule["id"], "operator": operator, "reason": problems.get(operator, "operator metrics missing")})
            continue
        value = get_path(payload, str(rule["metric"]))
        if value is None:
            no_data.append({"ruleId": rule["id"], "operator": operator, "metric": rule["metric"], "reason": "metric missing"})
            continue
        sample = _sample_size(payload, operator, cfg)
        min_sample = int(rule.get("minSample") or 0)
        if min_sample > 0 and (sample is None or sample < min_sample):
            insufficient.append(
                {
                    "ruleId": rule["id"],
                    "operator": operator,
                    "metric": rule["metric"],
                    "minSample": min_sample,
                    "sampleSize": sample,
                }
            )
            continue
        evaluated += 1

        op = str(rule["op"])
        level = None
        triggered = None
        if op == "eq":
            if compare(value, op, rule.get("warn")):
                level = str(rule.get("level") or "warning")
                triggered = {"op": op, "value": rule.get("warn")}
        else:
            critical = rule.get("critical")
            warn = rule.get("warn")
            if critical is not None and compare(value, op, critical):
                level = "critical"
                triggered = {"op": op, "value": critical}
            elif warn is not None and compare(value, op, warn):
                level = "warning"
                triggered = {"op": op, "value": warn}
        if level is None:
            continue
        items.append(
            {
                "id": f"{rule['id']}-{operator}",
                "ruleId": rule["id"],
                "type": rule["type"],
                "level": level,
                "severity": int(severity.get(level, 1)),
                "operator": operator,
                "metric": rule["metric"],
                "value": value,
                "threshold": {
                    "op": op,
                    "warn": rule.get("warn"),
                    "critical": rule.get("critical"),
                    "triggered": triggered,
                },
                "minSample": min_sample,
                "sampleSize": sample,
                "scope": rule.get("scope"),
                "suggestion": rule.get("suggestion"),
                "evidence": {
                    "operator": operator,
                    "metric": rule["metric"],
                    "value": value,
                    "metricsPath": evidence_paths.get(operator),
                },
            }
        )

    # 去重：同一 operator+type 保留最高等级，合并证据。
    dedup_key = str(cfg["dedupe"]["key"])
    grouped: dict[str, dict[str, Any]] = {}
    for item in items:
        key = f"{item['operator']}|{item['type']}" if dedup_key == "operator+type" else item["id"]
        current = grouped.get(key)
        if current is None:
            grouped[key] = {**item, "evidenceList": [item["evidence"]], "ruleIds": [item["ruleId"]]}
            continue
        current["evidenceList"].append(item["evidence"])
        current["ruleIds"].append(item["ruleId"])
        if item["severity"] > current["severity"]:
            for field in ("id", "ruleId", "level", "severity", "value", "threshold", "minSample", "sampleSize", "scope", "suggestion"):
                current[field] = item[field]

    deduped = sorted(
        grouped.values(),
        key=lambda item: (-item["severity"], item["operator"], item["type"]),
    )
    suppressed: list[dict[str, Any]] = []
    if cfg["suppression"].get("enabled"):
        max_per_type = int(cfg["suppression"]["maxPerType"])
        kept: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for item in deduped:
            count = counts.get(item["type"], 0)
            if count >= max_per_type:
                suppressed.append({"id": item["id"], "type": item["type"], "level": item["level"]})
                continue
            counts[item["type"]] = count + 1
            kept.append(item)
        deduped = kept

    max_risks = int(cfg["limits"]["maxRisks"])
    if len(deduped) > max_risks:
        suppressed.extend(
            {"id": item["id"], "type": item["type"], "level": item["level"], "reason": "MAX_RISKS"}
            for item in deduped[max_risks:]
        )
        deduped = deduped[:max_risks]

    return {
        "risks": deduped,
        "evaluatedRules": evaluated,
        "rawHits": len(items),
        "dedupedCount": len(grouped),
        "suppressed": suppressed,
        "suppressedCount": len(suppressed),
        "noData": no_data,
        "insufficientSample": insufficient,
        "outdated": cfg["outdated"],
        "definition": (
            "规则 DSL：op ∈ lt/gt/le/ge/eq/ne；双阈值 critical/warn 分别定级；"
            "minSample 用配置的样本量路径校验；去重按 operator+type 保留最高等级；"
            "抑制按类型上限保留高等级条目。"
        ),
    }
