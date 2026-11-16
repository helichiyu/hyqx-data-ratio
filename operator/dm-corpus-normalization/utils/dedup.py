"""去重：精确哈希组 + SimHash 分带近重复 + 图像 pHash 近重复。

不丢弃记录，只给出重复组与 ``duplicateOf`` 标记，供下游按策略筛选。
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            if left_root < right_root:
                self.parent[right_root] = left_root
            else:
                self.parent[left_root] = right_root


def find_duplicates(
    records: list[dict[str, Any]], cfg: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    dedup_cfg = cfg["dedup"]
    union = _UnionFind()
    by_id = {record["record_id"]: record for record in records}
    for record_id in by_id:
        union.find(record_id)

    exact: dict[str, list[str]] = defaultdict(list)
    for record in records:
        sha = str((record.get("metadata") or {}).get("sha256") or "")
        if sha:
            exact[sha].append(record["record_id"])
    for members in exact.values():
        for member in members[1:]:
            union.union(members[0], member)

    near_stats = {"textPairs": 0, "imagePairs": 0}
    _near_duplicates(
        records,
        union,
        modal="text",
        hash_field="simhash",
        max_distance=int(dedup_cfg["simhashMaxDistance"]),
        bands=int(dedup_cfg["simhashBands"]),
        max_candidates=int(dedup_cfg["maxCandidatesPerBand"]),
        stats_key="textPairs",
        stats=near_stats,
    )
    _near_duplicates(
        records,
        union,
        modal="image",
        hash_field="phash",
        max_distance=int(dedup_cfg["phashMaxDistance"]),
        bands=4,
        max_candidates=int(dedup_cfg["maxCandidatesPerBand"]),
        stats_key="imagePairs",
        stats=near_stats,
    )

    components: dict[str, list[str]] = defaultdict(list)
    for record_id in sorted(by_id):
        components[union.find(record_id)].append(record_id)

    groups: list[dict[str, Any]] = []
    duplicate_of: dict[str, str] = {}
    exact_groups = 0
    near_groups = 0
    for members in components.values():
        if len(members) < 2:
            continue
        members = sorted(members)
        representative = members[0]
        shas = {
            str((by_id[member].get("metadata") or {}).get("sha256") or "") for member in members
        }
        if len(shas) == 1:
            kind = "exact"
            evidence = {"sha256": next(iter(shas))}
            exact_groups += 1
        else:
            modalities = {by_id[member]["modal"] for member in members}
            if modalities == {"text"}:
                kind = "near_text"
                values = [_hash_int(by_id[m]["hashes"].get("simhash")) for m in members]
                evidence = {"maxDistance": _max_distance(values), "metric": "simhash64"}
            else:
                kind = "near_image"
                values = [_hash_int(by_id[m]["hashes"].get("phash")) for m in members]
                evidence = {"maxDistance": _max_distance(values), "metric": "phash64"}
            near_groups += 1
        group_id = "dup_" + hashlib.sha256(
            "\0".join(members).encode("utf-8")
        ).hexdigest()[:12]
        groups.append(
            {
                "groupId": group_id,
                "kind": kind,
                "representative": representative,
                "members": members,
                "count": len(members),
                "modalities": sorted({by_id[member]["modal"] for member in members}),
                "evidence": evidence,
            }
        )
        for member in members[1:]:
            duplicate_of[member] = representative

    groups.sort(key=lambda item: item["groupId"])
    stats = {
        "groups": len(groups),
        "exactGroups": exact_groups,
        "nearGroups": near_groups,
        "duplicateRecords": len(duplicate_of),
        **near_stats,
        "simhashMaxDistance": int(dedup_cfg["simhashMaxDistance"]),
        "phashMaxDistance": int(dedup_cfg["phashMaxDistance"]),
    }
    return groups, duplicate_of, stats


def _near_duplicates(
    records: list[dict[str, Any]],
    union: _UnionFind,
    *,
    modal: str,
    hash_field: str,
    max_distance: int,
    bands: int,
    max_candidates: int,
    stats_key: str,
    stats: dict[str, Any],
) -> None:
    band_bits = 64 // max(1, bands)
    band_mask = (1 << band_bits) - 1
    buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
    by_id = {record["record_id"]: record for record in records}
    for record in sorted(records, key=lambda item: item["record_id"]):
        if record["modal"] != modal:
            continue
        value = _hash_int((record.get("hashes") or {}).get(hash_field))
        if value is None:
            continue
        record_id = record["record_id"]
        for band in range(bands):
            band_value = (value >> (band * band_bits)) & band_mask
            key = (band, band_value)
            candidates = buckets[key]
            for candidate_id in candidates[-max_candidates:]:
                candidate = by_id[candidate_id]
                other = _hash_int((candidate.get("hashes") or {}).get(hash_field))
                if other is None:
                    continue
                if (value ^ other).bit_count() <= max_distance:
                    union.union(record_id, candidate_id)
                    stats[stats_key] += 1
            candidates.append(record_id)


def _hash_int(value: Any) -> int | None:
    if not value:
        return None
    try:
        return int(str(value), 16)
    except ValueError:
        return None


def _max_distance(values: list[int | None]) -> int | None:
    usable = [value for value in values if value is not None]
    if len(usable) < 2:
        return None
    return max(
        (left ^ right).bit_count()
        for index, left in enumerate(usable)
        for right in usable[index + 1 :]
    )
