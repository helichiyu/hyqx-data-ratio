"""哈希工具：md5/sha256、64 位 SimHash、64 位感知哈希（pHash）。

来源：本文件由 S0 模板派生（operators/_template，2026-11-16），S1 按任务书
OP-01 任务卡实现。全部为确定性算法，不使用 ``hash()``（受 PYTHONHASHSEED 影响）。
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import numpy as np

_CHUNK = 1024 * 1024
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")


def file_hashes(path: str | Path) -> tuple[str, str]:
    """流式计算文件 MD5 与 SHA-256。"""

    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with Path(path).open("rb") as source:
        while True:
            chunk = source.read(_CHUNK)
            if not chunk:
                break
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def bytes_hashes(payload: bytes) -> tuple[str, str]:
    return (
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def simhash64(text: str) -> str | None:
    """64 位 SimHash；空文本返回 None。

    - 英文/数字按词切分，中文按单字切分；
    - 词频作为权重；
    - 每个 token 用 blake2b 摘要取前 8 字节，按位投票。
    """

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


def simhash_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    return (int(left, 16) ^ int(right, 16)).bit_count()


def phash64(path: str | Path) -> str | None:
    """64 位 pHash：32×32 灰度 → DCT-II → 左上 8×8 → 中位数阈值。

    第 0 位为 DC 系数（均值亮度 >128），其余 63 位为 AC 系数是否高于中位数。
    与常见 pHash 实现兼容的 64 位十六进制输出，便于汉明距离去重。
    """

    from PIL import Image

    with Image.open(path) as image:
        gray = image.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
        pixels = np.asarray(gray, dtype=np.float64)

    matrix = _dct_matrix(32)
    coefficients = matrix @ pixels @ matrix.T
    low = coefficients[:8, :8]
    ac_values = low.flatten()[1:]
    median = float(np.median(ac_values))
    bits = 0
    dc_bit = 1 if low[0, 0] / 8.0 > 128.0 else 0
    bits |= dc_bit << 63
    for index, value in enumerate(ac_values):
        if value > median:
            bits |= 1 << (62 - index)
    return f"{bits:016x}"


def phash_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _dct_matrix(size: int) -> np.ndarray:
    matrix = np.zeros((size, size), dtype=np.float64)
    factor = math.pi / (2 * size)
    for row in range(size):
        scale = math.sqrt(1 / size) if row == 0 else math.sqrt(2 / size)
        for column in range(size):
            matrix[row, column] = scale * math.cos((2 * column + 1) * row * factor)
    return matrix
