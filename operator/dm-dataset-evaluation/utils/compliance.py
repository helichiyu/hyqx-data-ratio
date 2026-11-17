"""合规词表与版权哈希检测；资源缺失时明确 unavailable，不编造结果。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_terms(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, list):
            return [str(item) for item in payload if str(item).strip()]
        return None
    return [line.strip() for line in text.splitlines() if line.strip()]


def load_hashes(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if not isinstance(payload, list):
            return None
        return {str(item).strip().lower() for item in payload if str(item).strip()}
    return {line.strip().lower() for line in text.splitlines() if line.strip()}


def evaluate(
    sampled: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    terms: list[str] | None,
    hashes: set[str] | None,
    max_hits: int,
) -> dict[str, Any]:
    if terms is None and hashes is None:
        return {
            "status": "unavailable",
            "reasonCode": "COMPLIANCE_RESOURCES_REQUIRED",
            "message": "未提供合规词表/版权哈希库（Q-08/H-08），不做合规判定。",
            "hits": [],
            "hitRate": None,
        }
    normalized_terms = [term.lower() for term in (terms or [])]
    term_hits: list[dict[str, Any]] = []
    hash_hits: list[dict[str, Any]] = []
    for item in sampled:
        record = records.get(item["record_id"]) or {}
        text = str(record.get("text") or "").lower()
        if normalized_terms and text:
            matched = [term for term in normalized_terms if term in text]
            if matched:
                term_hits.append({"record_id": item["record_id"], "terms": matched[:10]})
        if hashes:
            try:
                hashes_json = json.loads(record.get("hashes_json") or "{}")
            except json.JSONDecodeError:
                hashes_json = {}
            candidates = {
                str(hashes_json.get("sha256") or "").lower(),
                str(hashes_json.get("md5") or "").lower(),
            } - {""}
            matched_hashes = sorted(candidates & hashes)
            if matched_hashes:
                hash_hits.append({"record_id": item["record_id"], "hashes": matched_hashes})
    hit_ids = {item["record_id"] for item in term_hits} | {item["record_id"] for item in hash_hits}
    count = len(sampled) or 1
    hits = (term_hits + hash_hits)[:max_hits]
    return {
        "status": "ok",
        "termsProvided": len(normalized_terms),
        "hashesProvided": len(hashes or set()),
        "termHits": len(term_hits),
        "hashHits": len(hash_hits),
        "hitCount": len(hit_ids),
        "hitRate": round(len(hit_ids) / count, 10),
        "passRate": round(1 - len(hit_ids) / count, 10),
        "hits": hits,
        "definition": "命中 = 正文包含任一敏感词，或记录 SHA-256/MD5 命中版权哈希库；hitRate = 命中记录数 / 抽样数。",
    }
