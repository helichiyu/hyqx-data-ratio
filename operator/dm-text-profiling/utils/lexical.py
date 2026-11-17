"""词汇丰富度：TTR、MSTTR、MTLD。

- TTR = 唯一 token 数 / 总 token 数（对长度敏感）；
- MSTTR = 每 50 token 窗口内唯一率，再对窗口均值（尾部不足窗口按实际长度）；
- MTLD = 平均因子长度（TTR 降到阈值 0.72 时为一个因子），双向平均。
"""

from __future__ import annotations

from typing import Any


def ttr(tokens: list[str]) -> float | None:
    if not tokens:
        return None
    return round(len(set(tokens)) / len(tokens), 6)


def msttr(tokens: list[str], window: int) -> float | None:
    if not tokens:
        return None
    window = max(2, int(window))
    ratios = []
    for start in range(0, len(tokens), window):
        chunk = tokens[start : start + window]
        if chunk:
            ratios.append(len(set(chunk)) / len(chunk))
    return round(sum(ratios) / len(ratios), 6) if ratios else None


def _mtld_direction(tokens: list[str], threshold: float) -> float:
    factors = 0.0
    seen: set[str] = set()
    count = 0
    for token in tokens:
        count += 1
        seen.add(token)
        if count >= 10 and len(seen) / count <= threshold:
            factors += 1.0
            seen = set()
            count = 0
    if count > 0:
        factors += (1.0 - len(seen) / count) / (1.0 - threshold)
    return len(tokens) / factors if factors > 0 else float(len(tokens))


def mtld(tokens: list[str], threshold: float = 0.72) -> float | None:
    if not tokens:
        return None
    forward = _mtld_direction(tokens, threshold)
    backward = _mtld_direction(list(reversed(tokens)), threshold)
    return round((forward + backward) / 2.0, 6)


def summary(tokens: list[str], cfg: dict[str, Any]) -> dict[str, Any]:
    window = int(cfg["lexical"]["msttrWindow"])
    return {
        "tokenCount": len(tokens),
        "uniqueTokens": len(set(tokens)),
        "ttr": ttr(tokens),
        "msttr": msttr(tokens, window),
        "mtld": mtld(tokens),
        "msttrWindow": window,
        "meanTokenChars": (
            round(sum(len(token) for token in tokens) / len(tokens), 6) if tokens else None
        ),
    }
