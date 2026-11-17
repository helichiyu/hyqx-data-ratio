"""分句与分词：标点分句 + jieba 分词（中文）/正则（拉丁）。"""

from __future__ import annotations

import re
from typing import Any

LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
CJK = re.compile(r"[一-鿿]")


def split_sentences(text: str, cfg: dict[str, Any]) -> list[str]:
    terminators = "".join(cfg["segment"]["sentenceTerminators"])
    pattern = re.compile(f"[^{re.escape(terminators)}]+[{re.escape(terminators)}]?")
    return [match.group(0).strip() for match in pattern.finditer(text) if match.group(0).strip()]


def split_clauses(sentence: str, cfg: dict[str, Any]) -> list[str]:
    separators = "".join(cfg["segment"]["clauseSeparators"])
    pattern = re.compile(f"[^{re.escape(separators)}]+")
    return [match.group(0).strip() for match in pattern.finditer(sentence) if match.group(0).strip()]


def words(text: str, cfg: dict[str, Any]) -> list[str]:
    """返回按出现顺序的全部 token（小写），不做去重。

    - 拉丁串：按 ``LATIN_WORD`` 提取，避免 jieba 把标点并入；
    - 中文：jieba 切词，保留含汉字的 token；
    - 其它（数字/符号）忽略。
    """

    import jieba

    tokens: list[str] = []
    for raw in jieba.cut(text):
        latin = LATIN_WORD.findall(raw)
        if latin:
            tokens.extend(token.lower() for token in latin)
            continue
        token = raw.strip().lower()
        if token and token.isalnum() and CJK.search(token):
            tokens.append(token)
    return tokens
