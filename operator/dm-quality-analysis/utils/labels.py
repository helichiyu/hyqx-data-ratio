"""标签加载、标注覆盖与多模态一致性。

- 标注覆盖 = 至少一个标签的记录数 / 记录数；
- 多模态一致性 = 有 ``metadata.extra.derivedFrom`` 关联的模态对，其一级标签集合有交集
  的比例；无关联对时 ``unavailable``，不编造。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load(path: Path | None) -> dict[str, list[list[str]]]:
    if path is None or not path.is_file():
        return {}
    mapping: dict[str, list[list[str]]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            record_id = row.get("record_id")
            labels = row.get("labels") or []
            paths = [
                [str(item) for item in label["path"]]
                for label in labels
                if isinstance(label, dict) and isinstance(label.get("path"), list) and label["path"]
            ]
            if record_id:
                mapping[str(record_id)] = paths
    return mapping


def coverage(label_map: dict[str, list[list[str]]], record_ids: list[str]) -> dict[str, Any]:
    if not label_map:
        return {
            "status": "unavailable",
            "reasonCode": "LABELS_UNAVAILABLE",
            "note": "未提供 OP-05 打标结果（params.labels_path）。",
        }
    labeled = sum(1 for record_id in record_ids if label_map.get(record_id))
    total = len(record_ids)
    return {
        "status": "ok",
        "records": total,
        "labeledRecords": labeled,
        "coverage": round(labeled / total, 6) if total else 0.0,
        "unlabeledRecords": total - labeled,
    }


def counts(label_map: dict[str, list[list[str]]], level: int = 0) -> dict[str, int]:
    counter: dict[str, int] = {}
    for paths in label_map.values():
        seen: set[str] = set()
        for path in paths:
            key = "/".join(path[: level + 1])
            if key and key not in seen:
                seen.add(key)
                counter[key] = counter.get(key, 0) + 1
    return counter


def multimodal_consistency(records: list[dict[str, Any]], label_map: dict[str, list[list[str]]]) -> dict[str, Any]:
    if not label_map:
        return {"status": "unavailable", "reasonCode": "LABELS_UNAVAILABLE"}
    pairs = 0
    consistent = 0
    both_labeled = 0
    for record in records:
        extra = ((record.get("metadata") or {}).get("extra") or {})
        parent = extra.get("derivedFrom")
        child_id = record.get("record_id")
        if not parent or not child_id:
            continue
        pairs += 1
        child = label_map.get(str(child_id)) or []
        parent_labels = label_map.get(str(parent)) or []
        if not child or not parent_labels:
            continue
        both_labeled += 1
        child_level1 = {path[0] for path in child if path}
        parent_level1 = {path[0] for path in parent_labels if path}
        if child_level1 & parent_level1:
            consistent += 1
    if pairs == 0:
        return {
            "status": "unavailable",
            "reasonCode": "NO_MULTIMODAL_PAIR",
            "note": "记录中没有 derivedFrom 跨模态关联对。",
        }
    return {
        "status": "ok",
        "pairs": pairs,
        "bothLabeled": both_labeled,
        "consistent": consistent,
        "consistency": round(consistent / both_labeled, 6) if both_labeled else None,
    }
