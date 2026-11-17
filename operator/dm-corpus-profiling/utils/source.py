"""六类来源分布与 AHP 可信度。

- 来源类来自记录 ``source`` 字段（OP-02 按 ``baseline/source-map.json`` 归类）；
- 每类四项分：authority/transparency 来自配置（联调初值），freshness 由记录 dt
  实时计算，evaluation 取该类 ``quality.completeness`` 均值；
- 总分 = Σ 维度权重 × 维度分；语料总分 = Σ 类占比 × 类总分。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from . import ahp


def _age_bucket(dt: str | None, as_of: date) -> str | None:
    if not dt:
        return None
    try:
        value = date.fromisoformat(dt[:10])
    except ValueError:
        return None
    days = (as_of - value).days
    if days <= 365:
        return "last_1y"
    if days <= 365 * 3:
        return "last_3y"
    return "older"


def freshness_score(dts: list[str | None], as_of: date, weights: dict[str, float], neutral: float) -> dict[str, Any]:
    buckets = {"last_1y": 0, "last_3y": 0, "older": 0}
    unknown = 0
    for dt in dts:
        bucket = _age_bucket(dt, as_of)
        if bucket is None:
            unknown += 1
        else:
            buckets[bucket] += 1
    known = sum(buckets.values())
    score = (
        sum(buckets[key] / known * float(weights[key]) for key in buckets) if known else neutral
    )
    return {
        "score": round(float(score), 6),
        "buckets": buckets,
        "unknown": unknown,
        "knownShare": round(known / len(dts), 6) if dts else 0.0,
        "neutralUsed": known == 0,
    }


def class_scores(
    counts: dict[str, int],
    dts: dict[str, list[str | None]],
    completeness: dict[str, list[float]],
    config: dict[str, Any],
    as_of: date,
) -> dict[str, Any]:
    ahp_cfg = config["ahp"]
    dimensions = ahp_cfg["dimensions"]
    check = ahp.consistency(ahp_cfg["matrix"])
    weights = dict(zip(dimensions, check["weights"]))
    fresh_cfg = config["freshness"]
    total = sum(counts.values())
    classes: dict[str, Any] = {}
    overall = 0.0
    for name in config["sourceClasses"]:
        count = counts.get(name, 0)
        base = ahp_cfg["sourceScores"][name]
        fresh = freshness_score(
            dts.get(name, []), as_of, fresh_cfg["weights"], float(fresh_cfg["neutral"])
        )
        values = {
            "authority": float(base["authority"]),
            "transparency": float(base["transparency"]),
            "freshness": fresh["score"],
            "evaluation": (
                round(sum(completeness[name]) / len(completeness[name]), 6)
                if completeness.get(name)
                else 0.0
            ),
        }
        score = sum(weights[dim] * values[dim] for dim in dimensions)
        share = count / total if total else 0.0
        overall += share * score
        classes[name] = {
            "count": count,
            "share": round(share, 6),
            "sharePercent": round(share * 100, 6),
            "dimensionScores": {dim: round(values[dim], 6) for dim in dimensions},
            "credibility": round(score, 6),
            "freshnessDetail": fresh,
        }
    unclassified = [name for name in counts if name not in config["sourceClasses"]]
    return {
        "ahp": {
            "dimensions": dimensions,
            "weights": {dim: weights[dim] for dim in dimensions},
            "lambdaMax": check["lambdaMax"],
            "ci": check["ci"],
            "cr": check["cr"],
            "consistencyMax": ahp_cfg["consistencyMax"],
            "consistent": check["cr"] < float(ahp_cfg["consistencyMax"]),
        },
        "classes": classes,
        "shareSumPercent": round(
            sum(item["sharePercent"] for item in classes.values()), 4
        ),
        "shareSumOk": abs(sum(item["sharePercent"] for item in classes.values()) - 100.0) <= 1e-4,
        "unexpectedSourceAliases": unclassified,
        "corpusCredibility": round(overall, 6),
        "asOf": as_of.isoformat(),
    }
