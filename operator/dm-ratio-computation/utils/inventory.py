"""标签库存：按（标签路径 × 来源）统计条数与 token 近似。

上游：OP-05 `result.jsonl`（`labels[].path`）与 OP-02 `records.jsonl`（`source`、`text`）。
无 OP-05 时 inventory 为空，返回 `LABELS_UNAVAILABLE`，不编造库存。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_labels(path: Path | None, level: int) -> dict[str, list[tuple[str, float]]]:
    """返回 ``{label_path: [(source, unit_size), ...]}``；unit_size 在合并 OP-02 后填充。"""
    if path is None or not path.is_file():
        return {}
    mapping: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            record_id = str(row.get("record_id") or "")
            for label in row.get("labels") or []:
                if not isinstance(label, dict):
                    continue
                path_value = label.get("path")
                if not isinstance(path_value, list) or not path_value:
                    continue
                key = "/".join(str(item) for item in path_value[:level])
                mapping[key].append((record_id, 1.0))
    return dict(mapping)


def merge_records(
    labels: dict[str, list[tuple[str, float]]],
    records_path: Path | None,
) -> dict[str, dict[str, float]]:
    """把每条标签条目映射到 source，并用文本字符数近似 token。"""

    sources: dict[str, str] = {}
    chars: dict[str, float] = {}
    if records_path is not None and records_path.is_file():
        with records_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                record_id = str(record.get("record_id") or "")
                if not record_id:
                    continue
                sources[record_id] = str(record.get("source") or "unknown")
                text = record.get("text")
                chars[record_id] = float(len(text)) if isinstance(text, str) else 0.0

    inventory: dict[str, dict[str, float]] = {}
    for label_path, entries in labels.items():
        bucket: dict[str, float] = defaultdict(float)
        for record_id, unit in entries:
            source = sources.get(record_id, "unknown")
            bucket[source] += unit
            if chars.get(record_id):
                bucket[f"__chars__{source}"] += chars[record_id]
        inventory[label_path] = dict(bucket)
    return inventory


def summarize(inventory: dict[str, dict[str, float]]) -> dict[str, Any]:
    labels = len(inventory)
    total = sum(
        value for bucket in inventory.values() for key, value in bucket.items() if not key.startswith("__")
    )
    by_source: dict[str, float] = defaultdict(float)
    for bucket in inventory.values():
        for key, value in bucket.items():
            if not key.startswith("__"):
                by_source[key] += value
    return {
        "labels": labels,
        "totalRecords": int(total),
        "bySource": {key: int(value) for key, value in sorted(by_source.items())},
    }
