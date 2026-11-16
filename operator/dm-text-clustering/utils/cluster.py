"""K 搜索、KMeans 聚类、轮廓系数与 c-TF-IDF 主题词。"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np

_EN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def cluster_vectors(
    vectors: np.ndarray,
    *,
    seed: int,
    cfg: dict[str, Any],
    fixed_k: int | None = None,
) -> dict[str, Any]:
    from sklearn.cluster import KMeans, MiniBatchKMeans
    from sklearn.metrics import silhouette_score

    n = int(vectors.shape[0])
    if n == 0:
        return {
            "k": 0,
            "labels": [],
            "silhouette": None,
            "search": [],
            "distances": [],
            "centroids": np.zeros((0, vectors.shape[1]), dtype=np.float32),
            "deterministic": True,
        }
    if n == 1 or _is_constant(vectors):
        labels = np.zeros(n, dtype=int)
        centroid = vectors.mean(axis=0, keepdims=True)
        distances = np.linalg.norm(vectors - centroid, axis=1)
        return {
            "k": 1,
            "labels": labels.tolist(),
            "silhouette": None,
            "search": [],
            "distances": distances.tolist(),
            "centroids": centroid.astype(np.float32),
            "deterministic": True,
        }

    clustering = cfg["clustering"]
    lower = max(int(clustering["minK"]), int(math.ceil(math.sqrt(n / 2))))
    upper = min(int(clustering["maxK"]), int(math.floor(4 * math.sqrt(n))), n)
    lower = max(2, min(lower, upper))
    if fixed_k is not None:
        lower = upper = max(1, min(int(fixed_k), n))
        search = _search(vectors, [lower], seed, cfg, silhouette_score)
    elif upper > lower:
        coarse_step = max(1, int(clustering["coarseStep"]))
        candidates = list(range(lower, upper + 1, coarse_step))
        if candidates[-1] != upper:
            candidates.append(upper)
        search = _search(vectors, candidates, seed, cfg, silhouette_score)
        best = max(search, key=lambda item: (item["silhouette"], -item["k"]))
        radius = max(1, int(clustering["refineRadius"]))
        refine = [
            k for k in range(max(lower, best["k"] - radius), min(upper, best["k"] + radius) + 1)
            if k not in candidates
        ]
        if refine:
            search.extend(_search(vectors, refine, seed, cfg, silhouette_score))
    else:
        search = _search(vectors, [max(1, lower)], seed, cfg, silhouette_score)

    best = max(search, key=lambda item: (item["silhouette"], -item["k"]))
    model = _fit(vectors, best["k"], seed, cfg, KMeans, MiniBatchKMeans)
    labels = model.labels_.astype(int)
    distances = np.linalg.norm(vectors - model.cluster_centers_[labels], axis=1)
    return {
        "k": int(best["k"]),
        "labels": labels.tolist(),
        "silhouette": float(best["silhouette"]),
        "search": search,
        "distances": distances.tolist(),
        "centroids": model.cluster_centers_.astype(np.float32),
        "deterministic": True,
    }


def ctfidf_topics(
    texts: list[str], labels: list[int], k: int, cfg: dict[str, Any]
) -> dict[int, list[str]]:
    topics_cfg = cfg["topics"]
    stopwords = set(topics_cfg["stopwords"])
    min_chars = int(topics_cfg["minTermChars"])
    top_n = int(topics_cfg["topTerms"])

    token_counts: dict[int, Counter[str]] = defaultdict(Counter)
    totals: Counter[int] = Counter()
    doc_freq: dict[str, int] = defaultdict(int)
    for text, label in zip(texts, labels):
        tokens = _tokenize(text, stopwords, min_chars)
        token_counts[int(label)].update(tokens)
        totals[int(label)] += len(tokens)
        for token in set(tokens):
            doc_freq[token] += 1

    num_clusters = max(1, k)
    result: dict[int, list[str]] = {}
    for label in range(num_clusters):
        counter = token_counts.get(label, Counter())
        total = max(1, totals.get(label, 0))
        scored = []
        for term, count in counter.items():
            tf = count / total
            idf = math.log(1 + num_clusters / max(1, doc_freq[term]))
            scored.append((tf * idf, term))
        scored.sort(key=lambda item: (-item[0], item[1]))
        result[label] = [term for _, term in scored[:top_n]]
    return result


def _search(vectors: np.ndarray, candidates: list[int], seed: int, cfg: dict[str, Any],
            silhouette_score) -> list[dict[str, Any]]:
    from sklearn.cluster import KMeans, MiniBatchKMeans

    results: list[dict[str, Any]] = []
    sample_size = min(len(vectors), int(cfg["clustering"]["silhouetteSample"]))
    for k in candidates:
        if k < 2 or k > len(vectors):
            continue
        model = _fit(vectors, k, seed, cfg, KMeans, MiniBatchKMeans)
        labels = model.labels_
        distinct = len(set(labels.tolist()))
        if distinct < 2 or distinct >= len(vectors):
            score = 0.0
        else:
            score = float(
                silhouette_score(
                    vectors, labels, sample_size=sample_size, random_state=seed
                )
            )
        results.append({"k": int(k), "silhouette": round(score, 6)})
    if not results:
        results = [{"k": min(2, len(vectors)), "silhouette": 0.0}]
    return results


def _fit(vectors: np.ndarray, k: int, seed: int, cfg: dict[str, Any], kmeans_cls, minibatch_cls):
    params = {
        "n_clusters": int(k),
        "random_state": seed,
        "n_init": int(cfg["clustering"]["nInit"]),
        "max_iter": int(cfg["clustering"]["maxIter"]),
    }
    if len(vectors) > int(cfg["clustering"]["miniBatchThreshold"]):
        return minibatch_cls(batch_size=min(4096, len(vectors)), **params).fit(vectors)
    return kmeans_cls(**params).fit(vectors)


def _is_constant(vectors: np.ndarray) -> bool:
    if len(vectors) <= 1:
        return True
    return bool(np.allclose(vectors, vectors[0], atol=1e-8))


def _tokenize(text: str, stopwords: set[str], min_chars: int) -> list[str]:
    import jieba

    lowered = (text or "").lower()
    tokens = [token.strip() for token in jieba.lcut(lowered) if token.strip()]
    tokens.extend(match.group(0).lower() for match in _EN_TOKEN.finditer(lowered))
    result: list[str] = []
    for token in tokens:
        if len(token) < min_chars or token in stopwords:
            continue
        if all(char.isdigit() or char.isspace() for char in token):
            continue
        result.append(token)
    return result
