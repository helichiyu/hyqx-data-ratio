"""向量索引：复用 OP-03 向量，构建确定性 IVF 近似索引并评估 recall@k/QPS。

精确内积检索作为金标准；IVF 用 MiniBatchKMeans（固定 seed）建簇，
查询只在 nprobe 个最近簇中检索，recall@k = 近似 topK 与精确 topK 的交集比例。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import MiniBatchKMeans


def load_vectors(vectors_path: Path, ids_path: Path, dimension: int) -> tuple[np.ndarray, list[dict[str, Any]]]:
    vectors = np.load(vectors_path)
    if vectors.ndim != 2:
        raise ValueError(f"vectors.npy 必须是二维矩阵，实际 {vectors.shape}")
    if vectors.shape[1] != dimension:
        raise ValueError(f"向量维度 {vectors.shape[1]} 与配置 {dimension} 不一致")
    ids = []
    with ids_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                ids.append(json.loads(stripped))
    if len(ids) != vectors.shape[0]:
        raise ValueError(f"向量数 {vectors.shape[0]} 与 id 数 {len(ids)} 不一致")
    return vectors.astype(np.float32), ids


def normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).astype(np.float32)


def _topk(scores: np.ndarray, k: int, exclude: int) -> list[int]:
    if scores.size == 0:
        return []
    scores = scores.copy()
    if 0 <= exclude < scores.size:
        scores[exclude] = -np.inf
    k = min(k, max(0, scores.size - (1 if 0 <= exclude < scores.size else 0)))
    if k <= 0:
        return []
    indices = np.argpartition(-scores, k - 1)[:k]
    return [int(index) for index in indices[np.argsort(-scores[indices])]]


def build_index(
    vectors: np.ndarray,
    ids: list[dict[str, Any]],
    cfg: dict[str, Any],
    seed: int,
    output_dir: Path,
) -> dict[str, Any]:
    normalized = normalize(vectors)
    count = normalized.shape[0]
    nlist = min(int(cfg["vector"]["nlist"]), max(1, count))
    nprobe = min(int(cfg["vector"]["nprobe"]), nlist)
    started = time.time()
    if count >= nlist:
        model = MiniBatchKMeans(
            n_clusters=nlist,
            random_state=seed,
            n_init=3,
            batch_size=min(1024, max(32, count)),
        )
        model.fit(normalized)
        centroids = model.cluster_centers_.astype(np.float32)
        assignments = model.labels_.astype(np.int32)
    else:
        centroids = normalized.copy()
        assignments = np.arange(count, dtype=np.int32)
    build_seconds = round(time.time() - started, 6)

    index_dir = output_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "vectors.npy", normalized)
    np.save(index_dir / "centroids.npy", centroids)
    np.save(index_dir / "assignments.npy", assignments)
    digest = hashlib.sha256()
    digest.update(normalized.tobytes())
    digest.update(centroids.tobytes())
    digest.update(assignments.tobytes())
    digest.update(json.dumps(cfg["vector"], sort_keys=True).encode("utf-8"))
    index_version = digest.hexdigest()[:16]

    top_k = int(cfg["vector"]["topK"])
    query_count = min(int(cfg["vector"]["queryCount"]), count)
    queries = list(range(query_count))
    recalls = {int(k): [] for k in cfg["vector"]["recallK"]}
    results = []
    query_started = time.time()
    for query_index in queries:
        query = normalized[query_index]
        exact_scores = normalized @ query
        exact = _topk(exact_scores, top_k, query_index)
        centroid_scores = centroids @ query
        cluster_order = np.argsort(-centroid_scores)[:nprobe]
        candidates = np.where(np.isin(assignments, cluster_order))[0]
        candidate_scores = normalized[candidates] @ query
        order = np.argsort(-candidate_scores)
        approx = [int(candidates[index]) for index in order if int(candidates[index]) != query_index][:top_k]
        for k in recalls:
            denominator = min(k, len(exact))
            recalls[k].append(
                len(set(approx[:k]) & set(exact[:k])) / denominator if denominator else 0.0
            )
        results.append(
            {
                "queryIndex": query_index,
                "recordId": ids[query_index].get("record_id"),
                "topK": [
                    {
                        "row": index,
                        "recordId": ids[index].get("record_id"),
                        "score": round(float(exact_scores[index]), 6),
                    }
                    for index in exact
                ],
                "approxTopK": [
                    {
                        "row": index,
                        "recordId": ids[index].get("record_id"),
                        "score": round(float(exact_scores[index]), 6),
                    }
                    for index in approx
                ],
            }
        )
    query_seconds = max(time.time() - query_started, 1e-9)

    meta = {
        "indexVersion": index_version,
        "count": count,
        "dimension": int(normalized.shape[1]),
        "nlist": nlist,
        "nprobe": nprobe,
        "topK": top_k,
        "queryCount": query_count,
        "recallAtK": {str(k): round(float(np.mean(values)), 6) if values else None for k, values in recalls.items()},
        "qps": round(query_count / query_seconds, 3),
        "buildSeconds": build_seconds,
        "seed": seed,
        "normalize": "l2",
        "method": "IVF (MiniBatchKMeans) + exact-inner-product baseline",
        "files": ["index/vectors.npy", "index/centroids.npy", "index/assignments.npy", "index/meta.json"],
    }
    (index_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"meta": meta, "results": results, "normalized": normalized}
