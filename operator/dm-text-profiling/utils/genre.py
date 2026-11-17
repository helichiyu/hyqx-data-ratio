"""语体分类：关键词规则（可解释）。

对每个语体统计命中关键词数，取得分最高者；置信度 = 命中数 / 该语体关键词总数，
未命中任何规则时为 ``general``，置信度 0。
"""

from __future__ import annotations

from typing import Any


def classify(text: str, cfg: dict[str, Any]) -> dict[str, Any]:
    rules: dict[str, list[str]] = cfg["genre"]["rules"]
    scores = {
        genre: sum(1 for keyword in keywords if keyword in text)
        for genre, keywords in rules.items()
    }
    best = max(scores, key=lambda name: (scores[name], name))
    if scores[best] == 0:
        return {
            "genre": cfg["genre"]["default"],
            "confidence": 0.0,
            "scores": scores,
            "reasonCode": "NO_GENRE_KEYWORD",
        }
    confidence = round(scores[best] / len(rules[best]), 6)
    return {"genre": best, "confidence": confidence, "scores": scores, "reasonCode": None}
