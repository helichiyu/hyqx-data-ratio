"""约束下建议配比、补数 TopN 与方案对标。

优化目标：在标签占比满足「合计 100%、单标签上下限、总改动上限」的前提下，
最小化 ``Σ_dim objectiveWeights(dim) × max(0, target(dim) - achieved(dim))``，
与达成度口径同向。求解用确定性 Frank-Wolfe（供体→受体转移 + 三分线搜索），
单纯形/上下界投影用于收缩与回退；不使用随机数。
归一化复用最大余数法（来源：OP-15 ``utils/weights.py`` 0.1.2），按配置精度取整，
保证合计严格 100% 且长尾不置零。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _project(vector: np.ndarray, lower: float, upper: float) -> np.ndarray:
    """投影到 {sum=1, lower<=x<=upper}；对偶变量二分，确定且无随机性。"""

    values = np.clip(np.asarray(vector, dtype=float), lower, upper)
    if abs(float(values.sum()) - 1.0) <= 1e-15:
        return values

    def total_at(tau: float) -> float:
        return float(np.clip(values - tau, lower, upper).sum())

    low = float(values.min()) - upper
    high = float(values.max()) - lower
    for _ in range(200):
        middle = (low + high) / 2.0
        if total_at(middle) > 1.0:
            low = middle
        else:
            high = middle
    return np.clip(values - (low + high) / 2.0, lower, upper)


def optimize(
    current: list[float],
    matrix: list[dict[str, float]],
    target: dict[str, float],
    dimensions: list[dict[str, Any]],
    objective_weights: dict[str, float],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """返回建议占比、目标函数变化、迭代次数与约束实测值。

    目标为各能力维度「目标亏空」的加权和（线性），与达成度口径严格同向：
    ``Σ w_dim·max(0, target−achieved)``。约束为单纯形+上下界+总改动上限。
    求解用 Frank-Wolfe（条件梯度）：每步在所有标签对中选最优「从高冗余标签转移到
    高缺口标签」方向，沿方向做凸函数精确线性搜索；全程确定、无随机数。
    """

    keys = [str(item["key"]) for item in dimensions]
    values = np.asarray(
        [[float(row.get(key, 0.0)) for key in keys] for row in matrix], dtype=float
    )
    start = np.asarray(current, dtype=float)
    target_vector = np.asarray([float(target.get(key, 0.0)) for key in keys], dtype=float)
    weights = np.asarray([float(objective_weights.get(key, 1.0)) for key in keys], dtype=float)
    lower = float(constraints["minLabelShare"])
    upper = float(constraints["maxLabelShare"])
    tolerance = float(constraints["tolerance"])
    max_iterations = int(constraints["maxIterations"])
    max_change = float(constraints["maxTotalChangeL1"])
    decimals = int(constraints["decimals"])
    # 预留最大余数取整可能带来的 L1 漂移，保证取整后仍满足改动上限。
    quantization_slack = len(start) * 0.5 * (10.0 ** (-decimals))

    def objective(vector: np.ndarray) -> float:
        achieved = values.T @ vector
        return float(np.sum(weights * np.maximum(0.0, target_vector - achieved)))

    def line_search(state: np.ndarray, donor: int, receiver: int, limit: float) -> float:
        """在 [0, limit] 上对凸的分段线性目标做三分搜索（确定性）。"""

        def value(step: float) -> float:
            candidate = state.copy()
            candidate[donor] -= step
            candidate[receiver] += step
            return objective(candidate)

        low, high = 0.0, limit
        for _ in range(120):
            first = low + (high - low) / 3.0
            second = high - (high - low) / 3.0
            if value(first) <= value(second):
                high = second
            else:
                low = first
        return (low + high) / 2.0

    initial = objective(start)
    state = _project(start, lower, upper)
    best = state.copy()
    best_value = objective(best)
    iterations = 0
    converged = False
    budget_bound = False
    for iterations in range(1, max_iterations + 1):
        achieved = values.T @ state
        active = achieved < target_vector - tolerance
        if not np.any(active):
            converged = True
            break
        # scores_i = 标签 i 对「缺口维度」的加权贡献；质量从贡献低的标签转移到贡献高的标签。
        # 供体必须仍有可减空间、受体必须仍有可加空间，避免选中已到边界的标签而空转。
        scores = values @ (weights * active.astype(float))
        donor_pool = np.where(state > lower + tolerance)[0]
        receiver_pool = np.where(state < upper - tolerance)[0]
        if donor_pool.size == 0 or receiver_pool.size == 0:
            converged = True
            break
        donor = int(donor_pool[np.argmin(scores[donor_pool])])
        receiver = int(receiver_pool[np.argmax(scores[receiver_pool])])
        if scores[receiver] - scores[donor] <= tolerance:
            converged = True
            break
        budget = (
            max_change
            - quantization_slack
            - float(np.abs(state - start).sum() / 2.0)
        )
        limit = min(
            float(state[donor] - lower),
            float(upper - state[receiver]),
            max(0.0, budget),
        )
        if limit <= tolerance:
            # 若方向仍可下降、仅因总改动预算耗尽而停步，如实记录「被改动上限截断」。
            if (
                budget <= tolerance
                and state[donor] - lower > tolerance
                and upper - state[receiver] > tolerance
                and scores[receiver] - scores[donor] > tolerance
            ):
                budget_bound = True
            converged = True
            break
        step = line_search(state, donor, receiver, limit)
        if step <= tolerance:
            converged = True
            break
        state[donor] -= step
        state[receiver] += step
        value = objective(state)
        if value < best_value:
            best_value = value
            best = state.copy()

    change = float(np.abs(best - start).sum() / 2.0)
    clipped = budget_bound
    if change > max_change > 0:
        alpha = max_change / change
        best = _project(start + alpha * (best - start), lower, upper)
        change = float(np.abs(best - start).sum() / 2.0)
        clipped = True

    shares = quantize([float(value) for value in best], decimals, lower)
    quantized = np.asarray(shares, dtype=float)
    reverted = False
    if objective(quantized) > initial + tolerance:
        # 取整后不应比当前方案更差；否则回退到当前方案，保证「预期提升」非负。
        shares = quantize([float(value) for value in start], decimals, lower)
        quantized = np.asarray(shares, dtype=float)
        reverted = True
    return {
        "shares": shares,
        "reverted": reverted,
        "iterations": iterations,
        "objectiveInitial": round(initial, 12),
        "objectiveFinal": round(objective(quantized), 12),
        "objectiveBest": round(best_value, 12),
        "changeL1": round(float(np.abs(quantized - start).sum() / 2.0), 10),
        "changeClipped": clipped,
        "converged": converged,
        "target": {key: round(float(target.get(key, 0.0)), 10) for key in keys},
        "objectiveWeights": {key: float(objective_weights.get(key, 1.0)) for key in keys},
    }


def quantize(shares: list[float], decimals: int, min_share: float) -> list[float]:
    """最大余数法取整；长尾至少 ``min_share``，合计严格为 1。"""

    if not shares or sum(float(share) for share in shares) <= 0:
        return [0.0 for _ in shares]
    if len(shares) * min_share > 1.0 + 1e-12:
        raise ValueError("min_share × 标签数 > 1，占比约束不可行")
    unit = 10 ** decimals
    raw = [float(share) * unit for share in shares]
    floors = [int(math.floor(value)) for value in raw]
    min_units = max(1, int(round(min_share * unit)))
    for index, share in enumerate(shares):
        if share > 0 and floors[index] < min_units:
            floors[index] = min_units
    remaining = unit - sum(floors)
    order = sorted(
        range(len(shares)),
        key=lambda index: (-(raw[index] - math.floor(raw[index])), index),
    )
    while remaining > 0:
        progressed = False
        for index in order:
            if remaining <= 0:
                break
            if floors[index] < unit:
                floors[index] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    while remaining < 0:
        candidates = [index for index in range(len(shares)) if floors[index] > min_units]
        if not candidates:
            break
        index = min(
            candidates,
            key=lambda item: (raw[item] - math.floor(raw[item]), item),
        )
        floors[index] -= 1
        remaining += 1
    return [round(units / unit, decimals) for units in floors]


def _allocate_integers(values: dict[str, float], total: int) -> dict[str, int]:
    """把浮点补样量按最大余数法分摊为整数，合计严格等于 ``total``。"""

    keys = sorted(values)
    if total <= 0:
        return {key: 0 for key in keys}
    weight = sum(max(0.0, float(values[key])) for key in keys)
    if weight <= 0:
        target = "unknown" if "unknown" in values else keys[0]
        return {key: (total if key == target else 0) for key in keys}
    scaled = {key: max(0.0, float(values[key])) / weight * total for key in keys}
    floors = {key: int(math.floor(scaled[key])) for key in keys}
    remaining = total - sum(floors.values())
    order = sorted(keys, key=lambda key: (-(scaled[key] - math.floor(scaled[key])), key))
    for index in range(max(0, remaining)):
        floors[order[index % len(order)]] += 1
    return floors


def check_constraints(
    shares: list[float],
    current: list[float],
    constraints: dict[str, Any],
    orientation: str,
) -> dict[str, Any]:
    """建议配比的硬约束核对；每项带实测值、阈值与说明。"""

    lower = float(constraints["minLabelShare"])
    upper = float(constraints["maxLabelShare"])
    max_change = float(constraints["maxTotalChangeL1"])
    total = sum(shares)
    minimum = min(shares) if shares else 0.0
    maximum = max(shares) if shares else 0.0
    change = sum(abs(left - right) for left, right in zip(shares, current)) / 2.0
    bound_ok = all(lower - 1e-12 <= value <= upper + 1e-12 for value in shares)
    checks = [
        {
            "id": "sum_100",
            "actual": round(total, 10),
            "threshold": 1.0,
            "tolerance": 1e-9,
            "passed": abs(total - 1.0) <= 1e-9,
            "source": "任务书 S4 门禁：占比合计 100%",
        },
        {
            "id": "label_bounds",
            "actual": {"min": minimum, "max": maximum},
            "threshold": {"min": lower, "max": upper},
            "passed": bound_ok,
            "source": "configs/analysis.json constraints.minLabelShare/maxLabelShare",
        },
        {
            "id": "change_limit",
            "actual": round(change, 10),
            "threshold": max_change,
            "passed": change <= max_change + 1e-9,
            "source": "configs/analysis.json constraints.maxTotalChangeL1（联调初值）",
        },
    ]
    return {
        "orientation": orientation,
        "checks": checks,
        "allPassed": all(item["passed"] for item in checks),
    }


def top_up(
    rows: list[dict[str, Any]],
    recommended: list[float],
    target_total: int,
    capability: dict[str, float],
    target: dict[str, float],
    source_weights: dict[str, dict[str, float]],
    dimensions: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """按真实库存计算缺口，按能力缺口方向推荐补数来源 TopN。"""

    keys = [str(item["key"]) for item in dimensions]
    sources = [source for source in cfg["capability"]["sources"] if source != "unknown"]
    deficits = {key: max(0.0, float(target.get(key, 0.0)) - float(capability.get(key, 0.0))) for key in keys}
    total_deficit = sum(deficits.values())
    if total_deficit > 0:
        direction = {key: value / total_deficit for key, value in deficits.items()}
    else:
        target_total_value = sum(float(value) for value in target.values()) or 1.0
        direction = {key: float(target.get(key, 0.0)) / target_total_value for key in keys}

    top_n = int(cfg["topUp"]["topN"])
    top_sources = int(cfg["topUp"]["recommendedSourcesPerLabel"])
    high_ratio = float(cfg["topUp"]["priorityHighRatio"])
    medium_ratio = float(cfg["topUp"]["priorityMediumRatio"])
    items: list[dict[str, Any]] = []
    source_totals: dict[str, float] = {source: 0.0 for source in sources}
    source_totals["unknown"] = 0.0
    predicted = {key: 0.0 for key in keys}
    predicted_mass = 0.0

    for row, share in zip(rows, recommended):
        feed = int(round(float(share) * target_total))
        inventory = int(row.get("count") or 0)
        gap = max(0, feed - inventory)
        existing = min(feed, inventory)
        mix = row.get("bySource") or {}
        total_mix = sum(float(item.get("effectiveCount") or 0.0) for item in mix.values() if isinstance(item, dict))
        existing_vector = {key: 0.0 for key in keys}
        if total_mix > 0:
            for source, item in mix.items():
                weight = float(item.get("effectiveCount") or 0.0) / total_mix
                for key in keys:
                    existing_vector[key] += weight * float(source_weights[source][key])
        for key in keys:
            predicted[key] += (existing / target_total) * existing_vector[key]
        predicted_mass += existing / target_total

        recommended_sources: list[dict[str, Any]] = []
        if gap > 0:
            alignment = {
                source: sum(direction[key] * float(source_weights[source][key]) for key in keys)
                for source in sources
            }
            ranked = sorted(alignment.items(), key=lambda pair: (-pair[1], pair[0]))[:top_sources]
            positive = [(source, value) for source, value in ranked if value > 0]
            if positive:
                alignment_total = sum(value for _, value in positive)
                recommendations = [
                    {"source": source, "alignment": round(value, 10), "shareOfGap": round(value / alignment_total, 10)}
                    for source, value in positive
                ]
            else:
                # 目标能力已达成但库存仍不足：按该标签现有已知来源构成补数，保持口径不变。
                fallback = sorted(
                    (
                        (source, float(item.get("effectiveCount") or 0.0) / total_mix)
                        for source, item in mix.items()
                        if total_mix > 0 and source in sources
                    ),
                    key=lambda pair: (-pair[1], pair[0]),
                )[:top_sources]
                fallback_total = sum(weight for _, weight in fallback)
                recommendations = (
                    [
                        {
                            "source": source,
                            "alignment": 0.0,
                            "shareOfGap": round(weight / fallback_total, 10),
                        }
                        for source, weight in fallback
                    ]
                    if fallback_total > 0
                    else []
                )
            if recommendations:
                allocated = sum(item["shareOfGap"] for item in recommendations)
                for item in recommendations:
                    if item["source"] in source_totals:
                        source_totals[item["source"]] += gap * item["shareOfGap"]
                    for key in keys:
                        predicted[key] += (
                            (gap / target_total)
                            * item["shareOfGap"]
                            * float(source_weights[item["source"]][key])
                        )
                predicted_mass += (gap / target_total) * allocated
            else:
                # 无可用来源映射的缺口单列，交由平台补采，不伪造推荐来源。
                source_totals["unknown"] += gap
            recommended_sources = recommendations
        items.append(
            {
                "label": row["label"],
                "level1": row.get("level1"),
                "feedCount": feed,
                "inventory": inventory,
                "gap": gap,
                "priority": (
                    "high"
                    if gap / target_total >= high_ratio
                    else ("medium" if gap / target_total >= medium_ratio else "low")
                )
                if gap > 0
                else "none",
                "recommendedSources": recommended_sources,
            }
        )

    ranked_items = sorted(items, key=lambda item: (-item["gap"], item["label"]))
    gaps = [item for item in ranked_items if item["gap"] > 0]
    top = gaps[:top_n]
    total_gap = sum(item["gap"] for item in items)
    if predicted_mass > 0:
        predicted = {key: predicted[key] / predicted_mass for key in keys}
    source_integers = _allocate_integers(source_totals, total_gap)
    return {
        "targetTotal": target_total,
        "totalGap": total_gap,
        "gapLabelCount": len(gaps),
        "items": ranked_items,
        "topN": top,
        "sourceTotals": source_integers,
        "predictedMass": round(predicted_mass, 10),
        "predictedCapability": {key: round(predicted[key], 10) for key in keys},
        "predictedCapabilityScore10": {
            key: round(predicted[key] * float(cfg["capability"]["scaleMax"]), 4) for key in keys
        },
        "definition": (
            "缺口 = round(建议占比×目标总量) − 该标签真实库存；来源推荐按目标能力缺口方向与"
            "来源能力映射的匹配度排序，补样量按匹配度分摊；无可用来源的缺口计入 unknown（需平台补采）。"
            "补齐后能力按现有库存与补数来源重新加权，并按总有效质量归一化；sourceTotals 用最大余数法"
            "取整，合计严格等于 totalGap。"
        ),
    }


def benchmark(
    scenarios: list[dict[str, Any]],
    profiles: dict[str, dict[str, float]],
    orientation: str,
    scale_max: float = 10.0,
) -> dict[str, Any]:
    """多方案对标矩阵；每个方案对全部目标模板给出达成度，按 orientation 选推荐方案。"""

    rows = []
    for scenario in scenarios:
        achievements = {
            name: round(
                float(
                    sum(
                        min(float(scenario["capability"].get(key, 0.0)), float(value))
                        for key, value in profile.items()
                    )
                    / (sum(profile.values()) or 1.0)
                ),
                10,
            )
            for name, profile in profiles.items()
        }
        rows.append(
            {
                "scenario": scenario["name"],
                "description": scenario.get("description"),
                "capability": {key: round(value, 10) for key, value in scenario["capability"].items()},
                "capabilityScore10": {
                    key: round(value * scale_max, 4) for key, value in scenario["capability"].items()
                },
                "achievement": achievements,
                "sourceShares": {key: round(value, 10) for key, value in scenario["sourceShares"].items()},
                "generalShare": round(float(scenario.get("generalShare") or 0.0), 10),
                "professionalShare": round(float(scenario.get("professionalShare") or 0.0), 10),
                "level1Coverage": round(float(scenario.get("level1Coverage") or 0.0), 6),
                "level2Coverage": round(float(scenario.get("level2Coverage") or 0.0), 6),
                "changeL1": round(float(scenario.get("changeL1") or 0.0), 10),
                "selected": scenario["name"] == orientation,
            }
        )
    selected = next((row for row in rows if row["selected"]), None)
    return {
        "orientation": orientation,
        "rows": rows,
        "recommendedScenario": selected["scenario"] if selected else None,
        "definition": (
            "达成度 = Σ_dim min(实际, 目标) / Σ_dim 目标（等价于 1 − 0.5·L1）；"
            "通用占比 = web_text+books+wiki+dialogue，专业占比 = code+science；"
            "改动量 = 0.5·Σ|建议占比−当前占比|。"
        ),
    }
