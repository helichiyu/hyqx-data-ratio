"""配比校验单：每项带实测值、阈值、来源与 pass/fail。

检查项：
1. 占比合计 = 100%（误差 ≤ `roundingErrorMax`）；
2. 核心标签（库存条数 ≥ `coreMinCount`）占比 ≥ `coverageMin`；
3. 一级类别覆盖 = 树中一级类别数（计划内出现即算覆盖）；
4. 二级类别覆盖 = 树中二级类别数；
5. 最小样本：`targetTotal ≥ minSample`；
6. 库存缺口：各标签 `feedCount` 不超过可用条数，缺口汇总。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_tree(path: Path) -> dict[str, list[str]]:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    nodes = snapshot["trees"]["content"]["nodes"]
    return {
        "level1": [node["nodeId"] for node in nodes if node["depth"] == 1],
        "level2": [node["nodeId"] for node in nodes if node["depth"] == 2],
        "treeVersion": snapshot.get("treeVersion"),
    }


def evaluate(rows: list[dict[str, Any]], normalization: dict[str, Any], tree: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    checks = []
    total_share = sum(row["share"] for row in rows)
    error = abs(total_share - 1.0)
    checks.append(
        {
            "id": "sum_100",
            "actual": round(total_share, 6),
            "threshold": 1.0,
            "tolerance": float(cfg["normalization"]["roundingErrorMax"]),
            "passed": error <= float(cfg["normalization"]["roundingErrorMax"]),
            "source": "任务书 S4 门禁 / baseline ratio.sum_target",
        }
    )

    core_min = int(cfg["coreLabels"]["coreMinCount"])
    core_share = sum(
        row["share"] for row in rows if row["count"] >= core_min
    )
    checks.append(
        {
            "id": "core_label_coverage",
            "actual": round(core_share, 6),
            "threshold": float(cfg["coreLabels"]["coverageMin"]),
            "excludedLabels": [row["label"] for row in rows if row["count"] < core_min][:20],
            "passed": core_share >= float(cfg["coreLabels"]["coverageMin"]),
            "source": "baseline coverage.core_label_min（H-03）",
        }
    )

    covered_level1 = {row["level1"] for row in rows if row["share"] > 0}
    covered_level2 = {row["level2"] for row in rows if row["share"] > 0}
    level1_rate = len(covered_level1) / len(tree["level1"]) if tree["level1"] else 0.0
    level2_rate = len(covered_level2) / len(tree["level2"]) if tree["level2"] else 0.0
    checks.append(
        {
            "id": "level1_coverage",
            "actual": round(level1_rate, 6),
            "threshold": float(cfg["targets"]["level1CoverageMin"]),
            "missing": sorted(set(tree["level1"]) - covered_level1)[:50],
            "passed": level1_rate >= float(cfg["targets"]["level1CoverageMin"]),
            "source": "baseline coverage.level1_min（H-03）",
        }
    )
    checks.append(
        {
            "id": "level2_coverage",
            "actual": round(level2_rate, 6),
            "threshold": float(cfg["targets"]["level2CoverageMin"]),
            "missing": sorted(set(tree["level2"]) - covered_level2)[:50],
            "passed": level2_rate >= float(cfg["targets"]["level2CoverageMin"]),
            "source": "baseline coverage.level2_min（H-03）",
        }
    )

    target_total = int(cfg["targets"]["targetTotal"])
    min_sample = int(cfg["targets"]["minSample"])
    checks.append(
        {
            "id": "min_sample",
            "actual": target_total,
            "threshold": min_sample,
            "passed": target_total >= min_sample,
            "source": "baseline sample.min_total（H-03）",
        }
    )

    gaps = []
    for row in rows:
        gap = max(0, int(row["feedCount"]) - int(row["count"]))
        if gap > 0:
            gaps.append({"label": row["label"], "feedCount": row["feedCount"], "inventory": row["count"], "gap": gap})
    total_gap = sum(item["gap"] for item in gaps)
    checks.append(
        {
            "id": "inventory_gap",
            "actual": total_gap,
            "threshold": 0,
            "gapLabels": gaps[:50],
            "passed": total_gap == 0,
            "source": "任务书 S4 门禁：库存折算",
        }
    )

    return {
        "checks": checks,
        "allPassed": all(item["passed"] for item in checks),
        "treeVersion": tree["treeVersion"],
        "uncoveredLevel1": sorted(set(tree["level1"]) - covered_level1),
        "uncoveredLevel2": sorted(set(tree["level2"]) - covered_level2),
        "totalGap": total_gap,
        "normalization": normalization,
    }
