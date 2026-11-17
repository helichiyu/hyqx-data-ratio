"""分层：source × cluster × quality，缺失维度统一标记 ``MISSING``。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_mapping(path: Path | None, key: str) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    mapping: dict[str, str] = {}
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
            value = row.get(key)
            if record_id is not None and value is not None:
                mapping[str(record_id)] = str(value)
    return mapping


def stratum_key(record: dict[str, Any], clusters: dict[str, str], qualities: dict[str, str], cfg: dict[str, Any]) -> str:
    missing = cfg["strata"]["missing"]
    record_id = str(record.get("record_id"))
    values = [
        str(record.get("source") or missing),
        clusters.get(record_id, missing),
        qualities.get(record_id, missing),
    ]
    return "|".join(values)
