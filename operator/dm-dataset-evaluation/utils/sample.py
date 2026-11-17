"""按模态分层的确定性抽样（5%–10%，固定 seed）。"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Any


def _order_key(seed: int, record_id: str) -> str:
    return hashlib.sha256(f"{seed}|{record_id}".encode("utf-8")).hexdigest()


def stratified_sample(
    records: dict[str, dict[str, Any]],
    ratio: float,
    seed: int,
    min_per_modal: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for record_id, record in records.items():
        modal = str(record.get("modal") or "unknown")
        groups[modal].append(record_id)

    sampled: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    for modal in sorted(groups):
        ids = sorted(groups[modal], key=lambda record_id: (_order_key(seed, record_id), record_id))
        take = max(int(min_per_modal), int(math.ceil(len(ids) * ratio)))
        take = min(take, len(ids))
        chosen = ids[:take]
        for rank, record_id in enumerate(chosen):
            sampled.append({"record_id": record_id, "modal": modal, "sampleRank": rank})
        stats[modal] = {
            "population": len(ids),
            "sampled": len(chosen),
            "ratio": round(len(chosen) / len(ids), 6) if ids else None,
        }
    total = len(records)
    return sampled, {
        "ratioRequested": ratio,
        "ratioEffective": round(len(sampled) / total, 6) if total else None,
        "population": total,
        "sampled": len(sampled),
        "perModal": stats,
        "orderHash": "sha256(seed|record_id)",
    }
