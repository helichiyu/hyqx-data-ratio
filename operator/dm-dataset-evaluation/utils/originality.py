"""原创性代理指标（Q-08，2026-11-18 用户口径：原创性不留空，自研代理）。

自研口径 = 语料内近重复/雷同检测：正文去空白后取字符 n-gram（shingle）集合，
抽样记录与全量语料两两算 Jaccard 相似度；近重复率 = 卷入近重复的抽样记录数 /
参与评估的抽样数，原创性分 = 1 - 近重复率。属**代理指标**，不冒充外部查重
结论；外部查重 API 到位后另行接入（配置/参数预留，不覆盖本代理）。
"""

from __future__ import annotations

from typing import Any

_SHINGLE_CAP = 2000


def _shingles(text: str, size: int) -> set[str]:
    compact = "".join(text.split())
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    grams = {compact[i : i + size] for i in range(len(compact) - size + 1)}
    if len(grams) <= _SHINGLE_CAP:
        return grams
    return set(sorted(grams)[:_SHINGLE_CAP])


def evaluate(
    sampled: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    shingle_size: int,
    threshold: float,
    max_pairs: int,
) -> dict[str, Any]:
    corpus: dict[str, set[str]] = {}
    for record_id, record in records.items():
        shingles = _shingles(str(record.get("text") or ""), shingle_size)
        if shingles:
            corpus[record_id] = shingles

    sampled_ids = [item["record_id"] for item in sampled if item["record_id"] in corpus]
    near_pairs: list[dict[str, Any]] = []
    involved: set[str] = set()
    max_similarity = 0.0
    for record_id in sampled_ids:
        base = corpus[record_id]
        for other_id, other in corpus.items():
            if other_id == record_id:
                continue
            union = len(base | other)
            if union == 0:
                continue
            similarity = len(base & other) / union
            if similarity > max_similarity:
                max_similarity = similarity
            if similarity >= threshold:
                near_pairs.append(
                    {"recordId": record_id, "otherId": other_id, "similarity": round(similarity, 6)}
                )
                involved.add(record_id)

    near_pairs.sort(key=lambda pair: (-pair["similarity"], pair["recordId"], pair["otherId"]))
    evaluated = len(sampled_ids) or 1
    near_dup_rate = round(len(involved) / evaluated, 10)
    return {
        "status": "ok",
        "method": "self_built_proxy",
        "definition": (
            "语料内近重复检测：正文字符 n-gram Jaccard 相似度；"
            "原创性分 = 1 - 近重复率。代理指标，不等同外部查重结论（Q-08，2026-11-18）。"
        ),
        "shingleSize": shingle_size,
        "nearDupThreshold": threshold,
        "sampledEvaluated": len(sampled_ids),
        "corpusSize": len(corpus),
        "nearDupPairs": len(near_pairs),
        "nearDupRate": near_dup_rate,
        "originalityScore": round(1 - near_dup_rate, 10),
        "maxSimilarity": round(max_similarity, 6),
        "topPairs": near_pairs[:max_pairs],
    }
