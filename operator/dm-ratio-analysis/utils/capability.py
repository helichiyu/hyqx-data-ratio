"""能力分、达成度与偏见指标。

能力分：``capability(dim) = Σ_label 标签占比 × 标签能力向量(dim)``；
贡献度逐标签可加总回能力分。达成度 = 目标 vs 实际（重叠度 = 1 - 0.5·L1）。
偏见指标对来源/领域分布计算基尼、HHI、归一化熵与头部占比，可复算。
"""

from __future__ import annotations

import math
from typing import Any


def score(
    matrix: list[dict[str, float]],
    dimensions: list[dict[str, Any]],
    shares: list[float],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """返回（能力向量, 逐标签贡献）；贡献不提前截断，保证可加总。"""

    keys = [str(item["key"]) for item in dimensions]
    vector = {key: 0.0 for key in keys}
    contributions: list[dict[str, Any]] = []
    for weight, row_vector in zip(shares, matrix):
        contribution = {key: float(weight) * float(row_vector[key]) for key in keys}
        for key in keys:
            vector[key] += contribution[key]
        contributions.append(contribution)
    return vector, contributions


def achievement(capability: dict[str, float], target: dict[str, float]) -> dict[str, Any]:
    """目标 vs 实际：逐维 ratio/gap + 整体重叠度 + L1 距离。"""

    per_dimension: dict[str, dict[str, Any]] = {}
    for key, target_value in target.items():
        actual = float(capability.get(key, 0.0))
        target_value = float(target_value)
        per_dimension[key] = {
            "actual": round(actual, 10),
            "target": target_value,
            "ratio": round(actual / target_value, 6) if target_value > 0 else None,
            "gap": round(target_value - actual, 10),
        }
    target_total = sum(float(value) for value in target.values())
    overlap = sum(
        min(float(capability.get(key, 0.0)), float(value)) for key, value in target.items()
    )
    l1 = sum(abs(float(capability.get(key, 0.0)) - float(value)) for key, value in target.items())
    return {
        "overall": round(overlap / target_total, 10) if target_total > 0 else None,
        "l1Distance": round(l1, 10),
        "dimensions": per_dimension,
    }


def _gini(values: list[float]) -> float | None:
    if not values:
        return None
    total = sum(values)
    if total <= 0:
        return None
    ordered = sorted(values)
    count = len(ordered)
    cumulative = sum((index + 1) * value for index, value in enumerate(ordered))
    return (2.0 * cumulative) / (count * total) - (count + 1.0) / count


def _hhi(values: list[float]) -> float | None:
    total = sum(values)
    if total <= 0:
        return None
    return sum((value / total) ** 2 for value in values)


def _entropy(values: list[float]) -> float | None:
    total = sum(values)
    count = len(values)
    if total <= 0 or count <= 1:
        return None
    entropy = -sum((value / total) * math.log(value / total) for value in values if value > 0)
    return entropy / math.log(count)


def distribution_metrics(values: list[float], cfg: dict[str, Any]) -> dict[str, Any]:
    """单一分布的偏见指标；阈值为联调初值，写入结果便于复核。"""

    total = sum(values)
    shares = [value / total for value in values] if total > 0 else []
    gini = _gini(values)
    hhi = _hhi(values)
    entropy = _entropy(values)
    top = max(shares) if shares else None
    bias_cfg = cfg["bias"]
    high = (gini is not None and gini >= float(bias_cfg["giniThreshold"])) or (
        hhi is not None and hhi >= float(bias_cfg["hhiHigh"])
    )
    medium = (gini is not None and gini >= float(bias_cfg["giniMedium"])) or (
        hhi is not None and hhi >= float(bias_cfg["hhiMedium"])
    ) or (entropy is not None and entropy <= float(bias_cfg["entropyMedium"]))
    level = "high" if high else ("medium" if medium else "low")
    return {
        "gini": round(gini, 10) if gini is not None else None,
        "hhi": round(hhi, 10) if hhi is not None else None,
        "normalizedEntropy": round(entropy, 10) if entropy is not None else None,
        "topShare": round(top, 10) if top is not None else None,
        "biasLevel": level,
        "thresholds": {
            "giniHigh": float(bias_cfg["giniThreshold"]),
            "giniMedium": float(bias_cfg["giniMedium"]),
            "hhiHigh": float(bias_cfg["hhiHigh"]),
            "hhiMedium": float(bias_cfg["hhiMedium"]),
            "entropyMedium": float(bias_cfg["entropyMedium"]),
        },
    }


def bias_report(
    source_distribution: dict[str, float],
    domain_distribution: dict[str, float],
    sources: list[str],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """来源与领域两组偏见指标；固定来源全集，缺失来源按 0 计入分布。"""

    source_values = [float(source_distribution.get(source, 0.0)) for source in sources]
    domain_values = list(domain_distribution.values())
    unknown_share = float(source_distribution.get("unknown", 0.0))
    return {
        "source": {
            **distribution_metrics(source_values, cfg),
            "shares": {source: round(float(source_distribution.get(source, 0.0)), 10) for source in sources},
            "unknownShare": round(unknown_share, 10),
        },
        "domain": {
            **distribution_metrics(domain_values, cfg),
            "categoryCount": len(domain_values),
        },
        "definition": "基尼/HHI/归一化熵对来源（固定六类，未知来源单列）与内容树一级领域分布计算",
    }
