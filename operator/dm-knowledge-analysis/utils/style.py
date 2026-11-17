"""语体与知识类型：关键词规则计数。

- 语体：每类命中关键词数取得分最高者，同分取字典序；
- 事实/推理/创意：三类关键词命中数，占比 = 该类命中 / 总命中；全 0 标 ``unknown``。
"""

from __future__ import annotations

from typing import Any


def _scores(text: str, rules: dict[str, list[str]]) -> dict[str, int]:
    return {name: sum(1 for keyword in keywords if keyword in text) for name, keywords in rules.items()}


def classify_style(text: str, cfg: dict[str, Any]) -> dict[str, Any]:
    scores = _scores(text, cfg["style"]["rules"])
    best = max(scores, key=lambda name: (scores[name], name))
    if scores[best] == 0:
        return {"style": cfg["style"]["default"], "confidence": 0.0, "scores": scores}
    return {
        "style": best,
        "confidence": round(scores[best] / len(cfg["style"]["rules"][best]), 6),
        "scores": scores,
    }


def classify_knowledge(text: str, cfg: dict[str, Any]) -> dict[str, Any]:
    scores = _scores(text, cfg["knowledge"]["ratioRules"])
    total = sum(scores.values())
    if total == 0:
        return {"type": "unknown", "scores": scores, "shares": {}, "totalHits": 0}
    best = max(scores, key=lambda name: (scores[name], name))
    return {
        "type": best,
        "scores": scores,
        "shares": {name: round(value / total, 6) for name, value in scores.items()},
        "totalHits": total,
    }
