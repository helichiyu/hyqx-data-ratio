"""地域统计：只使用记录 ``metadata`` 中显式地域字段，缺失时 unavailable。"""

from __future__ import annotations

from collections import Counter
from typing import Any


def collect(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    fields = list(cfg["region"]["fields"])
    counters = {field: Counter() for field in fields}
    records_with_region = 0
    for row in rows:
        metadata = row.get("metadata") or {}
        found = False
        for field in fields:
            value = metadata.get(field)
            if value:
                counters[field][str(value)] += 1
                found = True
        if found:
            records_with_region += 1
    if records_with_region == 0:
        return {
            "status": "unavailable",
            "reasonCode": "GEO_SOURCE_UNAVAILABLE",
            "note": "记录未提供 region/country/timezone 字段；不做 IP 或文本推断。",
        }
    return {
        "status": "ok",
        "recordsWithRegion": records_with_region,
        "recordCount": len(rows),
        "coverage": round(records_with_region / len(rows), 6) if rows else 0.0,
        "fields": {
            field: dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))
            for field, counter in counters.items()
        },
    }
