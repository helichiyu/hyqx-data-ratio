"""跨文档冲突：SimHash 近重复组 + 组内文本不一致。

口径：
- 对长度 >= ``minTextChars`` 的文本计算 64 位 SimHash（token 哈希加权）；
- 汉明距离 <= ``nearDuplicateDistance`` 视为近重复组；
- 组内去空白文本若存在两种以上，计一个冲突组；冲突率 = 冲突组 / 近重复组。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


def _weights(text: str) -> dict[str, int]:
    tokens = re.findall(r"[A-Za-z']+|[一-鿿]", text.lower())
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def simhash(text: str, bits: int = 64) -> int:
    vector = [0] * bits
    for token, weight in _weights(text).items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for index in range(bits):
            vector[index] += weight if (value >> index) & 1 else -weight
    result = 0
    for index, score in enumerate(vector):
        if score > 0:
            result |= 1 << index
    return result


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def analyze(texts: list[tuple[str, str]], cfg: dict[str, Any]) -> dict[str, Any]:
    """texts: [(record_id, text)]；返回近重复组、冲突组与冲突率。"""

    bits = int(cfg["conflict"]["simhashBits"])
    distance = int(cfg["conflict"]["nearDuplicateDistance"])
    min_chars = int(cfg["conflict"]["minTextChars"])
    candidates = [
        (record_id, re.sub(r"\s+", "", text), simhash(text, bits))
        for record_id, text in texts
        if text and len(text.strip()) >= min_chars
    ]
    groups: list[list[tuple[str, str, int]]] = []
    for item in candidates:
        for group in groups:
            if hamming(item[2], group[0][2]) <= distance:
                group.append(item)
                break
        else:
            groups.append([item])

    near_groups = [group for group in groups if len(group) > 1]
    conflicts = [
        group for group in near_groups if len({text for _, text, _ in group}) > 1
    ]
    return {
        "candidateRecords": len(candidates),
        "nearDuplicateGroups": len(near_groups),
        "nearDuplicateMembers": sum(len(group) for group in near_groups),
        "conflictGroups": len(conflicts),
        "conflictRate": round(len(conflicts) / len(near_groups), 6) if near_groups else 0.0,
        "conflictSamples": [
            {
                "members": [record_id for record_id, _, _ in group],
                "texts": len({text for _, text, _ in group}),
            }
            for group in conflicts[:20]
        ],
        "minTextChars": min_chars,
        "nearDuplicateDistance": distance,
    }
