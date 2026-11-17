"""标签→能力/领域映射。

- 能力映射：FGW 12.1 的「六类来源 → 模型能力」映射；标签能力向量 =
  该标签各来源有效条数占比 × 来源能力权重。每行来源权重合计 1，
  因此全部标签的能力贡献之和构成一个合计 1 的能力分布。
- 领域 rollup：按内容树一级/二级类别汇总占比，并给出未覆盖清单。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class MappingUnavailable(ValueError):
    """来源缺少能力映射，无法按 FGW 口径计算能力分。"""


def load_tree(path: Path) -> dict[str, Any]:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    nodes = snapshot["trees"]["content"]["nodes"]
    return {
        "level1": [node["nodeId"] for node in nodes if node["depth"] == 1],
        "level2": [node["nodeId"] for node in nodes if node["depth"] == 2],
        "treeVersion": snapshot.get("treeVersion"),
    }


def source_mix(row: dict[str, Any]) -> dict[str, float]:
    """单标签的来源构成（按有效条数归一）；无有效条数时返回空字典。"""

    bucket = row.get("bySource") or {}
    effective = {
        str(source): float(item.get("effectiveCount") or 0.0)
        for source, item in bucket.items()
        if isinstance(item, dict)
    }
    total = sum(effective.values())
    if total <= 0:
        return {}
    return {source: value / total for source, value in sorted(effective.items())}


def capability_matrix(
    rows: list[dict[str, Any]],
    dimensions: list[dict[str, Any]],
    source_weights: dict[str, dict[str, float]],
) -> list[dict[str, float]]:
    """逐标签计算能力向量；来源缺失映射时抛 ``MappingUnavailable``。"""

    keys = [str(item["key"]) for item in dimensions]
    matrix: list[dict[str, float]] = []
    for row in rows:
        mix = source_mix(row)
        vector = {key: 0.0 for key in keys}
        for source, share in mix.items():
            weights = source_weights.get(source)
            if weights is None:
                raise MappingUnavailable(f"来源 {source} 缺少能力映射（Q-05 映射库待提供）")
            missing = [key for key in keys if key not in weights]
            if missing:
                raise MappingUnavailable(f"来源 {source} 缺少能力维度 {missing}")
            for key in keys:
                vector[key] += share * float(weights[key])
        matrix.append(vector)
    return matrix


def domain_shares(
    rows: list[dict[str, Any]],
    tree: dict[str, Any],
    shares: list[float] | None = None,
) -> dict[str, Any]:
    """按内容树一级/二级类别汇总占比与未覆盖清单；可传入建议配比。"""

    level1: dict[str, float] = defaultdict(float)
    level2: dict[str, float] = defaultdict(float)
    for index, row in enumerate(rows):
        share = float((shares[index] if shares is not None else row.get("share")) or 0.0)
        level1[str(row.get("level1") or row["label"].split("/")[0])] += share
        level2[str(row.get("level2") or "/".join(row["label"].split("/")[:2]))] += share
    covered1 = {key for key, value in level1.items() if value > 0}
    covered2 = {key for key, value in level2.items() if value > 0}
    tree1 = tree["level1"]
    tree2 = tree["level2"]
    return {
        "level1Shares": {key: round(value, 10) for key, value in sorted(level1.items())},
        "level2Shares": {key: round(value, 10) for key, value in sorted(level2.items())},
        "level1Coverage": round(len(covered1) / len(tree1), 6) if tree1 else 0.0,
        "level2Coverage": round(len(covered2) / len(tree2), 6) if tree2 else 0.0,
        "uncoveredLevel1": sorted(set(tree1) - covered1),
        "uncoveredLevel2": sorted(set(tree2) - covered2),
        "treeLevel1Count": len(tree1),
        "treeLevel2Count": len(tree2),
    }


def source_shares(rows: list[dict[str, Any]], shares: list[float] | None = None) -> dict[str, float]:
    """按标签占比汇总来源占比；``shares`` 可传入建议配比，默认用 row['share']。"""

    totals: dict[str, float] = defaultdict(float)
    for index, row in enumerate(rows):
        share = float((shares[index] if shares is not None else row.get("share")) or 0.0)
        if share <= 0:
            continue
        for source, mix in source_mix(row).items():
            totals[source] += share * mix
    return {key: round(value, 10) for key, value in sorted(totals.items())}
