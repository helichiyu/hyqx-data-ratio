"""时间抽取与新鲜度：内容时间优先，缺失标 unknown，不猜测。

来源优先级（写入结果 ``timeSource``）：
1. ``metadata.capturedAt``（拍摄/采集时间，ISO 字符串）；
2. 正文中的 4 位年份（``yearMin``~``yearMax``，取首次出现）；
3. 无 → ``unknown``，不计入新鲜度分母；``partitions.dt`` 只是接入日期，不作为内容时间。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def extract(captured_at: Any, text: str | None, dt: Any, cfg: dict[str, Any]) -> dict[str, Any]:
    if captured_at:
        match = ISO_DATE.search(str(captured_at))
        if match:
            return _from_parts(match.group(1), match.group(2), "capturedAt")
        year_match = YEAR.search(str(captured_at))
        if year_match:
            return {"year": int(year_match.group(1)), "quarter": None, "timeSource": "capturedAt"}

    if text:
        limit = int(cfg["language"]["maxTextChars"])
        match = ISO_DATE.search(text[:limit])
        if match:
            return _from_parts(match.group(1), match.group(2), "text_iso_date")
        for candidate in YEAR.finditer(text[:limit]):
            year = int(candidate.group(1))
            if int(cfg["time"]["yearMin"]) <= year <= int(cfg["time"]["yearMax"]):
                return {"year": year, "quarter": None, "timeSource": "text_year"}

    return {"year": None, "quarter": None, "timeSource": "unknown"}


def _from_parts(year: str, month: str, source: str) -> dict[str, Any]:
    month_value = int(month)
    quarter = (month_value - 1) // 3 + 1
    return {"year": int(year), "quarter": quarter, "timeSource": source}


def age_bucket(year: int | None, as_of: date, cfg: dict[str, Any]) -> str | None:
    if year is None:
        return None
    days = (as_of - date(year, 12, 31)).days
    if days <= 365 * 1:
        return "last_1y"
    if days <= 365 * 3:
        return "last_3y"
    return "older"


def freshness(year: int | None, as_of: date, cfg: dict[str, Any]) -> float:
    weights = cfg["time"]["freshnessWeights"]
    bucket = age_bucket(year, as_of, cfg)
    if bucket is None:
        return 0.0
    return float(weights[bucket])
