"""WER/CER：文本归一化 + Levenshtein 编辑距离。

- CER：去空白与标点后按字符计算；
- WER：中文按字符（无分词依赖）、拉丁按词切分后计算；
- 无参考文本时不计算，返回 None（不冒充 WER）。
"""

from __future__ import annotations

import re
from typing import Any

PUNCT = re.compile(r"[\s　，。！？、；：,.!?;:\"'“”‘’（）()\[\]【】<>《》\-—…·]")
LATIN = re.compile(r"[A-Za-z']+")


def normalize(text: str) -> str:
    return PUNCT.sub("", text).lower()


def tokens(text: str) -> list[str]:
    lowered = text.lower()
    latin = LATIN.findall(lowered)
    if latin:
        return latin
    return list(normalize(lowered))


def levenshtein(left: list[str] | str, right: list[str] | str) -> int:
    a = list(left)
    b = list(right)
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for index, item in enumerate(a, start=1):
        current = [index]
        for position, other in enumerate(b, start=1):
            cost = 0 if item == other else 1
            current.append(min(previous[position] + 1, current[position - 1] + 1, previous[position - 1] + cost))
        previous = current
    return previous[-1]


def measure(hypothesis: str, reference: str | None) -> dict[str, Any]:
    if reference is None:
        return {
            "wer": None,
            "cer": None,
            "reasonCode": "REFERENCE_TEXT_REQUIRED",
            "referenceChars": None,
        }
    hyp_chars = normalize(hypothesis)
    ref_chars = normalize(reference)
    cer = round(levenshtein(hyp_chars, ref_chars) / len(ref_chars), 6) if ref_chars else None
    hyp_words = tokens(hypothesis)
    ref_words = tokens(reference)
    wer = round(levenshtein(hyp_words, ref_words) / len(ref_words), 6) if ref_words else None
    return {
        "wer": wer,
        "cer": cer,
        "reasonCode": None,
        "referenceChars": len(ref_chars),
        "hypothesisChars": len(hyp_chars),
    }
