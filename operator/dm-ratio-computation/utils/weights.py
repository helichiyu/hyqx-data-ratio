"""权重链路与最大余数归一化。

有效条数 = 条数 × 标签权重 × 来源权重 × 偏见降权 × 角色系数 × 阶段系数；
占比 = 有效条数 / Σ有效条数；整数化用最大余数法（单位 = 10^decimals），
合计恰好 100%；长尾至少保留 1 个单位（不置零）。
"""

from __future__ import annotations

import math
from typing import Any


def _coefficient(mapping: dict[str, float], key: str) -> float:
    if key in mapping:
        return float(mapping[key])
    return float(mapping.get("default", 1.0))


def compute_effective(
    inventory: dict[str, dict[str, float]],
    label_weights: dict[str, float],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    weights = cfg["weights"]
    rows = []
    for label_path in sorted(inventory):
        bucket = inventory[label_path]
        count = sum(value for key, value in bucket.items() if not key.startswith("__"))
        source_effective = 0.0
        for source, value in bucket.items():
            if source.startswith("__"):
                continue
            contribution = (
                value
                * _coefficient(weights["sourceWeights"], source)
                * _coefficient(weights["biasDownweights"], source)
                * _coefficient(weights["roleCoefficients"], source)
                * _coefficient(weights["stageCoefficients"], source)
            )
            source_effective += contribution
        label_weight = float(label_weights.get(label_path, weights["defaultLabel"]))
        effective = source_effective * label_weight
        rows.append(
            {
                "label": label_path,
                "level1": label_path.split("/")[0],
                "level2": "/".join(label_path.split("/")[:2]),
                "count": int(count),
                "labelWeight": label_weight,
                "effectiveCount": round(effective, 6),
            }
        )
    return rows


def normalize(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    decimals = int(cfg["normalization"]["decimals"])
    unit = 10 ** decimals
    total = sum(row["effectiveCount"] for row in rows)
    if total <= 0:
        for row in rows:
            row["share"] = 0.0
            row["feedCount"] = 0
        return {"total": 0.0, "unit": unit, "sumUnits": 0, "error": 0.0}

    raw = [row["effectiveCount"] / total * unit for row in rows]
    floors = [int(math.floor(value)) for value in raw]
    min_units = max(1, int(round(float(cfg["normalization"]["minShare"]) * unit)))
    for index, row in enumerate(rows):
        if row["effectiveCount"] > 0 and floors[index] < min_units:
            floors[index] = min_units
    remaining = unit - sum(floors)
    order = sorted(range(len(rows)), key=lambda index: (-(raw[index] - math.floor(raw[index])), rows[index]["label"]))
    while remaining > 0:
        progressed = False
        for index in order:
            if remaining <= 0:
                break
            floors[index] += 1
            remaining -= 1
            progressed = True
        if not progressed:
            break
    while remaining < 0:
        index = max(range(len(rows)), key=lambda position: (floors[position], rows[position]["label"]))
        if floors[index] <= min_units:
            break
        floors[index] -= 1
        remaining += 1

    target_total = float(cfg["targets"]["targetTotal"])
    for row, units in zip(rows, floors):
        row["share"] = round(units / unit, decimals)
        row["sharePercent"] = round(units / unit * 100, decimals - 2 if decimals >= 2 else decimals)
        row["feedCount"] = int(round(units / unit * target_total))
    error = abs(sum(row["share"] for row in rows) - 1.0)
    return {
        "total": round(total, 6),
        "unit": unit,
        "sumUnits": sum(floors),
        "error": round(error, 10),
        "targetTotal": int(target_total),
    }
