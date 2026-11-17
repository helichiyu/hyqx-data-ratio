"""句法近似指标：句长、从句数、从句深度、被动句、标点密度。

无依存句法模型，采用可解释规则：
- 从句数 = 分句数（逗号/顿号等分隔）；
- 从句深度 = 1 + 句内从属连词数（上限 4）；
- 被动句 = 命中「被/受到/遭到/给/为…所」规则。
"""

from __future__ import annotations

import re
from typing import Any

from . import segment

PASSIVE = re.compile(r"被|受到|遭到|为.{0,12}所")
TERMINAL = re.compile(r"[。！？!?；;]$")


def analyze(text: str, cfg: dict[str, Any]) -> dict[str, Any]:
    sentences = segment.split_sentences(text, cfg)
    sentence_chars = [len(sentence) for sentence in sentences]
    clause_counts = [len(segment.split_clauses(sentence, cfg)) for sentence in sentences]
    subordinators = cfg["syntax"]["subordinators"]
    depths = [1 + min(3, sum(1 for word in subordinators if word in sentence)) for sentence in sentences]
    passive = sum(1 for sentence in sentences if PASSIVE.search(sentence))
    complete = sum(1 for sentence in sentences if TERMINAL.search(sentence))
    punctuation = sum(1 for char in text if char in "，。！？、；：,!?;:")
    return {
        "sentenceCount": len(sentences),
        "sentenceCharsMean": round(sum(sentence_chars) / len(sentence_chars), 6) if sentences else None,
        "sentenceCharsMax": max(sentence_chars) if sentences else None,
        "clausesPerSentenceMean": round(sum(clause_counts) / len(clause_counts), 6) if sentences else None,
        "clauseDepthMean": round(sum(depths) / len(depths), 6) if depths else None,
        "passiveSentences": passive,
        "passiveRate": round(passive / len(sentences), 6) if sentences else None,
        "completeSentenceRate": round(complete / len(sentences), 6) if sentences else None,
        "punctuationPer100Chars": round(punctuation / len(text) * 100, 6) if text else None,
    }
