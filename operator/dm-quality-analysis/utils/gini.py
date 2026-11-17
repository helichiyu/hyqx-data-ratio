"""基尼系数：标签分布不均衡度（0 = 完全均衡，1 = 完全集中）。

公式：对排序后的数值 x_i（i=1..n），G = (2·Σ i·x_i)/(n·Σ x_i) − (n+1)/n。
"""

from __future__ import annotations

from typing import Any


def coefficient(values: list[float]) -> float | None:
    if not values or sum(values) <= 0:
        return None
    ordered = sorted(values)
    n = len(ordered)
    total = sum(ordered)
    weighted = sum((index + 1) * value for index, value in enumerate(ordered))
    return round((2 * weighted) / (n * total) - (n + 1) / n, 6)


def analyze(label_counts: dict[str, int], cfg: dict[str, Any]) -> dict[str, Any]:
    values = [float(count) for count in label_counts.values()]
    gini = coefficient(values)
    threshold = float(cfg["gini"]["threshold"])
    total = sum(label_counts.values())
    top = sorted(label_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    return {
        "status": "ok" if gini is not None else "unavailable",
        "gini": gini,
        "threshold": threshold,
        "exceedsThreshold": (gini is not None and gini > threshold),
        "labelCount": len(label_counts),
        "instanceCount": total,
        "topLabels": [
            {"path": path, "count": count, "share": round(count / total, 6) if total else 0.0}
            for path, count in top
        ],
    }
