"""完整率：必填字段存在性与文本空值。"""

from __future__ import annotations

from typing import Any


def evaluate(record: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    rules = cfg["completeness"]
    checks: dict[str, bool] = {}
    for field in rules["requiredFields"]:
        checks[field] = record.get(field) not in (None, "", [], {})
    metadata = record.get("metadata") or {}
    for field in rules["requiredMetadata"]:
        checks[f"metadata.{field}"] = metadata.get(field) not in (None, "")
    hashes = record.get("hashes") or {}
    for field in rules["requiredHashes"]:
        checks[f"hashes.{field}"] = hashes.get(field) not in (None, "")
    if record.get("modal") == "text":
        checks["text.nonEmpty"] = bool((record.get("text") or "").strip())
    present = sum(1 for value in checks.values() if value)
    rate = round(present / len(checks), 6) if checks else 0.0
    return {
        "rate": rate,
        "lowCompleteness": rate < float(rules["lowCompleteness"]),
        "missingFields": sorted(name for name, value in checks.items() if not value),
        "blankText": record.get("modal") == "text" and not (record.get("text") or "").strip(),
    }
