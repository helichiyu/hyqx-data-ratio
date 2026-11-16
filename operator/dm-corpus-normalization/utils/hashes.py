"""64 位 SimHash。

来源：复制自 ``operator/dm-multimodal-analysis/utils/hashes.py``（OP-01，版本 0.1.0），
按任务书 2.1 允许复制小函数并注明来源。文本归一化后需重算 SimHash。
"""

from __future__ import annotations

import hashlib
import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")


def simhash64(text: str) -> str | None:
    tokens = _TOKEN_RE.findall(text or "")
    if not tokens:
        return None
    weights: dict[str, int] = {}
    for token in tokens:
        lowered = token.lower()
        weights[lowered] = weights.get(lowered, 0) + 1
    vector = [0.0] * 64
    for token, weight in sorted(weights.items()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for bit in range(64):
            vector[bit] += weight if (value >> (63 - bit)) & 1 else -weight
    result = 0
    for bit, score in enumerate(vector):
        if score > 0:
            result |= 1 << (63 - bit)
    return f"{result:016x}"
