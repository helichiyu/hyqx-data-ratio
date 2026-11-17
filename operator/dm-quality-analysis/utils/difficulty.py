"""难度分档：文本复杂度 0–100 → 四档。

分项（权重见 configs/quality.json difficulty.weights）：
- sentenceLength：句均字符数映射到 0–100（8 字以下 0，60 字以上 100，线性）；
- clauseComplexity：句均从句数（1→0，5→100）；
- lexicalRarity：罕见词（全语料词频位于后 50%）比例 ×100。

无文本（图像/音频/视频）不打分，难度为 null。
"""

from __future__ import annotations

from typing import Any


def _linear(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def score(
    sentence_chars_mean: float | None,
    clauses_mean: float | None,
    rarity: float | None,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    weights = cfg["difficulty"]["weights"]
    parts = {
        "sentenceLength": _linear(sentence_chars_mean or 0.0, 8.0, 60.0),
        "clauseComplexity": _linear(clauses_mean or 1.0, 1.0, 5.0),
        "lexicalRarity": (rarity or 0.0) * 100.0,
    }
    total = sum(weights[name] * parts[name] for name in weights)
    level = None
    for band in cfg["difficulty"]["bands"]:
        if total <= band["max"]:
            level = band["level"]
            break
    return {
        "score": round(total, 6),
        "level": level,
        "components": {name: round(value, 6) for name, value in parts.items()},
        "weights": weights,
    }
