"""专家校验分层抽样：5%–10%、固定 seed、高风险必选。"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _top_label(row: dict[str, Any]) -> str | None:
    candidates = []
    for label in row.get("labels") or []:
        if isinstance(label, dict) and isinstance(label.get("path"), list) and label["path"]:
            path = "/".join(str(item) for item in label["path"])
            candidates.append((float(label.get("confidence") or 0.0), path))
    if not candidates:
        value = row.get("label")
        return str(value) if value else None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def load_objects(path: Path, max_records: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    objects = []
    failures = []
    if path.is_dir():
        candidate = path / "objects.jsonl"
        if not candidate.is_file():
            candidate = path / "result.jsonl"
        path = candidate
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if len(objects) >= max_records:
                failures.append({"id": f"line:{number}", "reasonCode": "OBJECT_LIMIT_EXCEEDED"})
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append({"id": f"line:{number}", "reasonCode": "OBJECT_JSON_INVALID", "detail": str(exc)})
                continue
            record_id = str(row.get("record_id") or "")
            label = row.get("label") or _top_label(row)
            if not record_id or not label:
                failures.append({"id": record_id or f"line:{number}", "reasonCode": "OBJECT_LABEL_MISSING"})
                continue
            level1 = row.get("level1") or str(label).split("/")[0]
            objects.append(
                {
                    "record_id": record_id,
                    "label": str(label),
                    "level1": level1,
                    "riskLevel": row.get("riskLevel"),
                    "modal": row.get("modal"),
                }
            )
    return objects, failures


def load_risk(path: Path | None) -> dict[str, str]:
    risks: dict[str, str] = {}
    if path is None or not path.is_file():
        return risks
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            record_id = str(row.get("record_id") or "")
            level = row.get("riskLevel") or row.get("level")
            if record_id and level:
                risks[record_id] = str(level)
    return risks


def sample(
    objects: list[dict[str, Any]],
    risks: dict[str, str],
    cfg: dict[str, Any],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sampling = cfg["sampling"]
    ratio = min(float(sampling["maxRatio"]), max(float(sampling["minRatio"]), float(sampling["ratio"])))
    min_per = int(sampling["minPerStratum"])
    high_levels = set(str(item) for item in sampling["highRiskLevels"])

    for obj in objects:
        if risks.get(obj["record_id"]):
            obj["riskLevel"] = risks[obj["record_id"]]

    stratum_field = str(sampling["stratumField"])
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for obj in objects:
        stratum = str(obj.get(stratum_field) or obj.get("level1") or "all")
        strata[stratum].append(obj)

    def order_key(obj: dict[str, Any]) -> tuple[str, str]:
        return hashlib.sha256(f"{seed}|{obj['record_id']}".encode("utf-8")).hexdigest(), obj["record_id"]

    population = len(objects)
    # 先定总样本量（5%–10%），再按层规模比例分配；每层至少 minPerStratum，
    # 避免「每层向上取整」导致小层多、总体比例远超 10%。
    target_total = min(population, max(len(strata), int(math.ceil(population * ratio))))
    quotas = {stratum: min(int(min_per), len(group)) for stratum, group in strata.items()}
    remaining = target_total - sum(quotas.values())
    if remaining > 0:
        weight_total = sum(len(group) for group in strata.values()) or 1
        raw = {stratum: remaining * len(group) / weight_total for stratum, group in strata.items()}
        floors = {stratum: int(math.floor(value)) for stratum, value in raw.items()}
        leftover = remaining - sum(floors.values())
        order = sorted(strata, key=lambda stratum: (-(raw[stratum] - floors[stratum]), stratum))
        for stratum in order[:leftover]:
            floors[stratum] += 1
        for stratum in strata:
            quotas[stratum] = min(len(strata[stratum]), quotas[stratum] + floors[stratum])

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    per_stratum: dict[str, Any] = {}
    for stratum in sorted(strata):
        group = sorted(strata[stratum], key=order_key)
        take = min(quotas[stratum], len(group))
        for obj in group[:take]:
            selected.append({**obj, "stratum": stratum, "selectedBy": "sample"})
            selected_ids.add(obj["record_id"])
        per_stratum[stratum] = {"population": len(group), "sampled": take, "ratio": round(take / len(group), 6) if group else None}

    high_risk_total = 0
    high_risk_selected = 0
    for obj in objects:
        if str(obj.get("riskLevel") or "") not in high_levels:
            continue
        high_risk_total += 1
        if obj["record_id"] in selected_ids:
            continue
        stratum = str(obj.get("level1") or "all")
        selected.append({**obj, "stratum": stratum, "selectedBy": "high_risk"})
        selected_ids.add(obj["record_id"])
        high_risk_selected += 1

    selected.sort(key=lambda item: item["record_id"])
    population = len(objects)
    stats = {
        "population": population,
        "targetTotal": target_total,
        "sampled": len(selected),
        "ratioRequested": ratio,
        "ratioEffective": round(len(selected) / population, 6) if population else None,
        "strataCount": len(strata),
        "perStratum": per_stratum,
        "highRiskTotal": high_risk_total,
        "highRiskAdded": sum(1 for item in selected if item["selectedBy"] == "high_risk"),
        "highRiskLevels": sorted(high_levels),
        "ratioWithinRange": float(sampling["minRatio"]) <= ratio <= float(sampling["maxRatio"]),
    }
    return selected, stats
