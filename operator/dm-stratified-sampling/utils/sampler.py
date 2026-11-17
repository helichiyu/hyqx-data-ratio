"""确定性抽样：sha256(seed|record_id) 升序取前 n_h，无放回、可复现。"""

from __future__ import annotations

import hashlib
from typing import Any


def order_value(seed: int, record_id: str) -> str:
    return hashlib.sha256(f"{seed}|{record_id}".encode("utf-8")).hexdigest()


def sample_stratum(records: list[str], quota: int, seed: int) -> list[dict[str, Any]]:
    if quota <= 0 or not records:
        return []
    ranked = sorted(records, key=lambda record_id: (order_value(seed, record_id), record_id))
    return [
        {"record_id": record_id, "hash": order_value(seed, record_id)}
        for record_id in ranked[:quota]
    ]
