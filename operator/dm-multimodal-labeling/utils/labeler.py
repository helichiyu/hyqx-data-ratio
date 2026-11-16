"""零样本打标：内容向量与标签向量余弦相似度 → topK 内 softmax → 阈值裁剪。

置信度定义：在 topK 候选内对余弦相似度做 softmax（温度 0.02），使 top1 落在 0–1；
同时要求绝对相似度 ≥ ``minSimilarity``、top1-top2 原始余弦差 ≥ ``marginThreshold``，
避免把“相对最好但绝对不相关”的标签写入结果。无证据/低置信进未归类池。
"""

from __future__ import annotations

from typing import Any

import numpy as np


def build_label_matrix(embedder, tree, cfg: dict[str, Any]) -> np.ndarray:
    return embedder.encode(tree.label_texts).astype(np.float32)


def label_text(
    embedder,
    label_matrix: np.ndarray,
    tree,
    text: str,
    cfg: dict[str, Any],
    *,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    vector = embedder.encode_document(text)
    return label_vector(embedder, label_matrix, tree, vector, cfg, evidence=evidence)


def label_vector(
    embedder,
    label_matrix: np.ndarray,
    tree,
    vector: np.ndarray,
    cfg: dict[str, Any],
    *,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    if not np.any(vector):
        return _unclassified("UNCLASSIFIED_NO_TEXT_EVIDENCE", evidence)
    similarities = label_matrix @ vector
    order = np.argsort(-similarities)
    top_k = max(1, int(cfg["labeling"]["topK"]))
    top_indices = order[:top_k]
    top_similarities = similarities[top_indices]
    temperature = max(float(cfg["labeling"]["temperature"]), 1e-6)
    shifted = top_similarities - float(top_similarities.max())
    probabilities = np.exp(shifted / temperature)
    probabilities = probabilities / probabilities.sum()

    top = [
        {
            "path": tree.labels[int(index)]["path"],
            "confidence": round(float(probabilities[position]), 6),
            "similarity": round(float(similarities[int(index)]), 6),
        }
        for position, index in enumerate(top_indices)
    ]
    best_index = int(order[0])
    second_index = int(order[1]) if len(order) > 1 else best_index
    top_similarity = float(similarities[best_index])
    margin = top_similarity - float(similarities[second_index])
    confidence = float(probabilities[0])

    reason = None
    if top_similarity < float(cfg["labeling"]["minSimilarity"]):
        reason = "UNCLASSIFIED_LOW_SIMILARITY"
    elif confidence < float(cfg["labeling"]["confidenceThreshold"]):
        reason = "UNCLASSIFIED_LOW_CONFIDENCE"
    elif margin < float(cfg["labeling"]["marginThreshold"]):
        reason = "UNCLASSIFIED_SMALL_MARGIN"
    if reason:
        return {
            "labels": [],
            "topK": top,
            "unclassified": True,
            "reasonCode": reason,
            "top1": round(confidence, 6),
            "margin": round(margin, 6),
            "evidence": evidence,
        }
    return {
        "labels": [
            {
                "path": tree.labels[best_index]["path"],
                "confidence": round(confidence, 6),
                "topK": top,
                "evidence": evidence,
                "modelVersion": embedder.model_version,
                "treeVersion": tree.tree_version,
            }
        ],
        "topK": top,
        "unclassified": False,
        "reasonCode": None,
        "top1": round(confidence, 6),
        "margin": round(margin, 6),
        "evidence": evidence,
    }


def fuse_vectors(vectors: list[np.ndarray], weights: list[float]) -> np.ndarray:
    if not vectors:
        return np.zeros(0, dtype=np.float32)
    stacked = np.stack(vectors, axis=0)
    weight_array = np.asarray(weights, dtype=np.float32)
    if weight_array.sum() <= 0:
        weight_array = np.ones_like(weight_array)
    weight_array = weight_array / weight_array.sum()
    fused = (stacked * weight_array[:, None]).sum(axis=0)
    norm = float(np.linalg.norm(fused))
    return fused / max(norm, 1e-12)


def _unclassified(reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "labels": [],
        "topK": [],
        "unclassified": True,
        "reasonCode": reason,
        "top1": None,
        "margin": None,
        "evidence": evidence,
    }
