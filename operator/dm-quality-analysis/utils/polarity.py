"""极性占比：情感词典 + 否定词翻转（规则，不做模型推断）。

score = (pos − neg) / (pos + neg)；|score| < ``neutralThreshold`` 判中性。
否定规则：情感词前 3 个字符内出现否定词，则该词极性翻转。
"""

from __future__ import annotations

import re
from typing import Any


def analyze(text: str, cfg: dict[str, Any]) -> dict[str, Any]:
    rule = cfg["polarity"]
    positive = list(rule["positive"])
    negative = list(rule["negative"])
    negations = list(rule["negations"])
    pos = 0
    neg = 0
    lowered = text.lower()
    for word in positive + negative:
        sign = 1 if word in positive else -1
        if re.fullmatch(r"[A-Za-z']+", word):
            pattern = re.compile(rf"\b{re.escape(word.lower())}\b")
            token = word.lower()
        else:
            pattern = re.compile(re.escape(word))
            token = word
        for match in pattern.finditer(lowered):
            window = lowered[max(0, match.start() - 3) : match.start()]
            flipped = any(negation in window for negation in negations)
            value = sign * (-1 if flipped else 1)
            if value > 0:
                pos += 1
            else:
                neg += 1
    total = pos + neg
    if total == 0:
        return {"polarity": "neutral", "score": 0.0, "positive": pos, "negative": neg}
    score = (pos - neg) / total
    threshold = float(rule["neutralThreshold"])
    label = "positive" if score > threshold else "negative" if score < -threshold else "neutral"
    return {"polarity": label, "score": round(score, 6), "positive": pos, "negative": neg}
