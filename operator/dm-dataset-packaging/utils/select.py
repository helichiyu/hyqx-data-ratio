"""确定性分层选样与断点续跑。

每个标签按其 OP-15 配额（``feedCount``）选样；标签内按 ``sha256(seed|record_id)``
升序取前 N，保证固定 seed 可复现、无随机数。记录只归属一个标签，因此不同标签
不会重复选中同一条记录；库存不足时如实记录缺口。checkpoint 每完成一个标签落盘，
重跑时从已完成标签之后继续，不重复、不丢样。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _order_key(seed: int, record_id: str) -> str:
    return hashlib.sha256(f"{seed}|{record_id}".encode("utf-8")).hexdigest()


def load_checkpoint(path: Path, params_hash: str, seed: int) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("paramsHash") != params_hash or int(payload.get("seed", -1)) != seed:
        return None
    if not isinstance(payload.get("completedLabels"), list):
        return None
    return payload


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def select(
    plan_rows: list[dict[str, Any]],
    assigned: dict[str, list[str]],
    seed: int,
    params_hash: str,
    checkpoint_path: Path,
    resume: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], bool]:
    """返回（入选记录, 逐标签配额表, checkpoint 载荷, 是否复用断点）。"""

    checkpoint = load_checkpoint(checkpoint_path, params_hash, seed) if resume else None
    completed = set(checkpoint.get("completedLabels") or []) if checkpoint else set()
    per_label: dict[str, dict[str, Any]] = dict(checkpoint.get("perLabel") or {}) if checkpoint else {}
    selected_ids: list[str] = list(checkpoint.get("selectedIds") or []) if checkpoint else []
    selected_set = set(selected_ids)
    resumed = checkpoint is not None and bool(completed)

    payload = {
        "version": "0.1.0",
        "paramsHash": params_hash,
        "seed": seed,
        "completedLabels": sorted(completed),
        "perLabel": per_label,
        "selectedIds": selected_ids,
    }

    rows = sorted(plan_rows, key=lambda row: str(row["label"]))
    for row in rows:
        label = str(row["label"])
        quota = max(0, int(row.get("feedCount") or 0))
        available = [record_id for record_id in assigned.get(label, []) if record_id not in selected_set]
        if label in completed:
            continue
        ordered = sorted(available, key=lambda record_id: (_order_key(seed, record_id), record_id))
        take = ordered[: min(quota, len(ordered))]
        for record_id in take:
            selected_set.add(record_id)
            selected_ids.append(record_id)
        selected_count = len(take)
        gap = max(0, quota - selected_count)
        if quota == 0:
            status = "zero_quota"
        elif not available:
            status = "no_inventory"
        elif gap > 0:
            status = "inventory_short"
        else:
            status = "ok"
        per_label[label] = {
            "label": label,
            "level1": row.get("level1") or label.split("/")[0],
            "level2": row.get("level2") or "/".join(label.split("/")[:2]),
            "quota": quota,
            "available": len(available),
            "selected": selected_count,
            "gap": gap,
            "rate": round(selected_count / quota, 6) if quota > 0 else None,
            "status": status,
            "recordIds": take,
        }
        completed.add(label)
        payload["completedLabels"] = sorted(completed)
        payload["perLabel"] = per_label
        payload["selectedIds"] = selected_ids
        save_checkpoint(checkpoint_path, payload)

    selected: list[dict[str, Any]] = []
    for row in rows:
        label = str(row["label"])
        entry = per_label.get(label) or {}
        for rank, record_id in enumerate(entry.get("recordIds") or []):
            selected.append(
                {
                    "record_id": record_id,
                    "label": label,
                    "level1": entry.get("level1"),
                    "level2": entry.get("level2"),
                    "selectionRank": rank,
                }
            )
    quotas = [per_label[str(row["label"])] for row in rows]
    return selected, quotas, payload, resumed


def bias_report(
    quotas: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    warn_threshold: float,
) -> dict[str, Any]:
    """逐标签实抽/配额偏差 + 来源分布偏差。"""

    deviations = []
    quota_deviations = []
    weighted = 0.0
    weight_sum = 0.0
    for entry in quotas:
        quota = int(entry["quota"])
        if quota <= 0:
            continue
        deviation = abs(int(entry["selected"]) - quota) / quota
        item = {
            "label": entry["label"],
            "quota": quota,
            "selected": entry["selected"],
            "deviation": round(deviation, 6),
            "status": entry["status"],
        }
        quota_deviations.append(item)
        # 只有配额真正满足的层才反映「抽样代表性偏差」；库存不足层的差异是缺口，单列。
        if entry["status"] == "ok":
            deviations.append(item)
        weighted += deviation * quota
        weight_sum += quota
    max_deviation = max((item["deviation"] for item in deviations), default=None)
    max_quota_deviation = max((item["deviation"] for item in quota_deviations), default=None)

    plan_by_label = {str(row["label"]): row for row in plan_rows}
    expected_sources: dict[str, float] = {}
    total_quota = sum(int(entry["quota"]) for entry in quotas)
    if total_quota > 0:
        for entry in quotas:
            quota = int(entry["quota"])
            if quota <= 0:
                continue
            bucket = plan_by_label.get(entry["label"], {}).get("bySource") or {}
            label_total = sum(float(item.get("effectiveCount") or 0.0) for item in bucket.values() if isinstance(item, dict))
            if label_total <= 0:
                continue
            for source, item in bucket.items():
                expected_sources[source] = expected_sources.get(source, 0.0) + (
                    quota / total_quota * float(item.get("effectiveCount") or 0.0) / label_total
                )
    actual_counts: dict[str, int] = {}
    for item in selected:
        record = records.get(item["record_id"]) or {}
        source = str((record.get("partitions") or {}).get("source") or record.get("source") or "unknown")
        actual_counts[source] = actual_counts.get(source, 0) + 1
    actual_total = sum(actual_counts.values()) or 1
    actual_sources = {source: count / actual_total for source, count in actual_counts.items()}
    source_deviation = {
        source: round(actual_sources.get(source, 0.0) - expected_sources.get(source, 0.0), 6)
        for source in sorted(set(actual_sources) | set(expected_sources))
    }
    max_source_deviation = max((abs(value) for value in source_deviation.values()), default=None)

    return {
        "perLabel": quota_deviations,
        "samplingDeviations": deviations,
        "weightedMeanDeviation": round(weighted / weight_sum, 6) if weight_sum > 0 else None,
        "maxDeviation": max_deviation,
        "maxQuotaDeviation": max_quota_deviation,
        "maxSourceDeviation": max_source_deviation,
        "sourceDeviation": source_deviation,
        "expectedSources": {key: round(value, 10) for key, value in sorted(expected_sources.items())},
        "actualSources": {key: round(value, 10) for key, value in sorted(actual_sources.items())},
        "warnThreshold": warn_threshold,
        "warn": (max_deviation is not None and max_deviation > warn_threshold)
        or (max_source_deviation is not None and max_source_deviation > warn_threshold),
        "definition": (
            "逐标签偏差 = |实抽−配额| / 配额；maxDeviation 只统计配额已满足（status=ok）的层，"
            "反映抽样代表性；maxQuotaDeviation 统计全部有配额的层，包含库存不足导致的缺口；"
            "来源偏差 = 实抽来源占比 − 按配额与 OP-15 bySource 折算的期望占比。"
        ),
    }
