"""Neyman 配额：``n_h = n · (N_h·CV_h) / Σ(N_h·CV_h)``。

- CV_h = 层内抽样单位（文本字符数/媒体字节数）的标准差/均值；CV=0 或全部为 0 时
  退化为按 N_h 比例分配；
- 浮点配额用最大余数法取整；n_h 不超过 N_h；
- 取整后按 ``minPerStratum`` 补最小配额（从高于最小值的层按配额从大到小借调），
  容量不足的余量写入 ``unmet``。
"""

from __future__ import annotations

import math
from typing import Any


def _cv(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance) / mean


def allocate(
    strata: dict[str, dict[str, Any]],
    target: int,
    min_per_stratum: int,
    max_per_stratum: dict[str, int],
) -> dict[str, Any]:
    keys = sorted(strata)
    sizes = {key: len(strata[key]["records"]) for key in keys}
    cvs = {key: _cv(strata[key]["values"]) for key in keys}
    weights = {key: sizes[key] * cvs[key] for key in keys}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        weights = {key: float(sizes[key]) for key in keys}
        total_weight = float(sum(sizes.values()))
        basis = "proportional(no-cv)"
    else:
        basis = "neyman"

    ideal = {key: (target * weights[key] / total_weight if total_weight else 0.0) for key in keys}
    caps = {key: min(sizes[key], int(max_per_stratum.get(key, sizes[key]))) for key in keys}

    assigned = {key: min(caps[key], int(math.floor(ideal[key]))) for key in keys}
    remaining = target - sum(assigned.values())
    order = sorted(keys, key=lambda key: (-(ideal[key] - math.floor(ideal[key])), key))
    while remaining > 0:
        progressed = False
        for key in order:
            if remaining <= 0:
                break
            if assigned[key] < caps[key]:
                assigned[key] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    unmet = max(0, remaining)

    enforced = True
    for key in keys:
        need = int(min_per_stratum) if sizes[key] else 0
        deficit = need - assigned[key]
        if deficit <= 0:
            continue
        donors = sorted(
            (other for other in keys if assigned[other] > min_per_stratum),
            key=lambda other: (-assigned[other], other),
        )
        for donor in donors:
            if deficit <= 0:
                break
            take = min(deficit, assigned[donor] - int(min_per_stratum))
            assigned[donor] -= take
            assigned[key] += take
            deficit -= take
        if deficit > 0:
            enforced = False
            unmet += deficit

    return {
        "basis": basis,
        "target": target,
        "quotas": assigned,
        "ideal": {key: round(ideal[key], 6) for key in keys},
        "cvs": {key: round(cvs[key], 6) for key in keys},
        "populations": sizes,
        "capacities": caps,
        "unmet": unmet,
        "minEnforced": enforced,
        "allocated": sum(assigned.values()),
    }
