"""热点/长尾：以批次最大时间为基准，窗口内为热点，其余为长尾；无时间标 unknown。"""

from __future__ import annotations

import re
from datetime import date
from typing import Any


def extract_year(captured_at: Any, text: str, pattern: str) -> int | None:
    for source in (captured_at, text):
        if not source:
            continue
        match = re.search(pattern, str(source))
        if match:
            return int(match.group(1))
    return None


def classify(year: int | None, as_of: date, window_days: int) -> str:
    if year is None:
        return "unknown"
    days = (as_of - date(year, 12, 31)).days
    return "hot" if days <= window_days else "long_tail"
