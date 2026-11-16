"""OP-03 纯函数单测：切窗、K 搜索、c-TF-IDF、边界。"""

from __future__ import annotations

import numpy as np

from op03_env import CORE


class _CharTokenizer:
    """按字符编码的测试 tokenizer，避免单测加载真实模型。"""

    def encode(self, text, add_special_tokens=False):
        return [ord(char) for char in text]

    def decode(self, ids, skip_special_tokens=True):
        return "".join(chr(int(item)) for item in ids)


def test_chunking_sentence_pack():
    cfg = CORE.load_config()
    tokenizer = _CharTokenizer()
    text = "第一句。" * 10 + "第二句。" * 10
    chunks = CORE.chunking.split_chunks(text, tokenizer, cfg)
    assert chunks
    assert all(len(tokenizer.encode(chunk)) <= cfg["chunking"]["maxTokens"] for chunk in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_chunking_long_sentence_hard_split():
    cfg = CORE.load_config()
    tokenizer = _CharTokenizer()
    text = "甲" * 1300
    chunks = CORE.chunking.split_chunks(text, tokenizer, cfg)
    assert len(chunks) == 3
    assert "".join(chunks) == text


def test_cluster_synthetic_three_groups():
    cfg = CORE.load_config()
    rng = np.random.default_rng(42)
    centers = np.eye(8, dtype=np.float32) * 5
    vectors = np.concatenate([center + rng.normal(0, 0.05, (20, 8)) for center in centers])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    result = CORE.cluster.cluster_vectors(
        vectors, seed=42, cfg=cfg, fixed_k=3
    )
    assert result["k"] == 3
    assert len(set(result["labels"])) == 3
    assert result["silhouette"] > 0.2
    assert len(result["distances"]) == len(vectors)


def test_cluster_constant_and_small():
    cfg = CORE.load_config()
    constant = np.ones((10, 8), dtype=np.float32)
    result = CORE.cluster.cluster_vectors(constant, seed=42, cfg=cfg)
    assert result["k"] == 1
    small = np.eye(3, dtype=np.float32)
    result = CORE.cluster.cluster_vectors(small, seed=42, cfg=cfg)
    assert result["k"] == 3
    assert len(set(result["labels"])) == 3


def test_ctfidf_topics():
    cfg = CORE.load_config()
    texts = [
        "机器学习模型训练与评估",
        "深度学习神经网络训练",
        "财经市场股票投资",
        "财经股票市场行情",
    ]
    topics = CORE.cluster.ctfidf_topics(texts, [0, 0, 1, 1], 2, cfg)
    assert "机器" in "".join(topics[0]) or "学习" in "".join(topics[0])
    assert "股票" in "".join(topics[1]) or "财经" in "".join(topics[1])
