"""领域覆盖：消费 OP-06 结果，按领域树 rollup 并计算四种覆盖率口径。

无上游领域标签时返回 ``unavailable`` + reasonCode，不猜测分布。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def load_tree(path: Path, space: str = "domain") -> dict[str, Any]:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    tree = snapshot["trees"][space]
    nodes = tree["nodes"]
    level1 = [node["nodeId"] for node in nodes if node["depth"] == 1]
    level2 = [node["nodeId"] for node in nodes if node["depth"] == 2]
    leaves = [node["nodeId"] for node in nodes if node.get("leaf")]
    return {
        "treeVersion": snapshot.get("treeVersion"),
        "level1": level1,
        "level2": level2,
        "leaves": leaves,
        "paths": {node["nodeId"]: node for node in nodes},
    }


def _iter_label_paths(path: Path) -> Iterable[list[str]]:
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            for label in row.get("domainLabels") or []:
                path_value = label.get("path")
                if isinstance(path_value, list) and path_value:
                    yield [str(item) for item in path_value]


def domain_coverage(result_path: Path | None, tree: dict[str, Any], text_records: int) -> dict[str, Any]:
    if result_path is None:
        return {
            "status": "unavailable",
            "reasonCode": "DOMAIN_LABELS_UNAVAILABLE",
            "note": "未提供 OP-06 领域标签结果目录（params.domain_labels_path 或上游输出）。",
        }
    if not result_path.is_file():
        return {
            "status": "unavailable",
            "reasonCode": "DOMAIN_LABELS_FILE_MISSING",
            "note": f"领域标签文件不存在：{result_path}",
        }

    level1_counts: dict[str, int] = {}
    level2_counts: dict[str, int] = {}
    leaf_counts: dict[str, int] = {}
    records_with_labels = 0
    records_seen = 0
    with result_path.open("r", encoding="utf-8") as source:
        for line in source:
            stripped = line.strip()
            if not stripped:
                continue
            records_seen += 1
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            labels = row.get("domainLabels") or []
            paths = [
                [str(item) for item in label.get("path")]
                for label in labels
                if isinstance(label, dict) and isinstance(label.get("path"), list) and label.get("path")
            ]
            if paths:
                records_with_labels += 1
            for path in paths:
                if len(path) >= 1:
                    level1_counts[path[0]] = level1_counts.get(path[0], 0) + 1
                if len(path) >= 2:
                    key = "/".join(path[:2])
                    level2_counts[key] = level2_counts.get(key, 0) + 1
                if len(path) >= 3:
                    key = "/".join(path[:3])
                    leaf_counts[key] = leaf_counts.get(key, 0) + 1

    denominator = text_records or records_seen or 1
    coverage = {
        "level1": round(len(level1_counts) / len(tree["level1"]), 6) if tree["level1"] else 0.0,
        "level2": round(len(level2_counts) / len(tree["level2"]), 6) if tree["level2"] else 0.0,
        "leaf": round(len(leaf_counts) / len(tree["leaves"]), 6) if tree["leaves"] else 0.0,
        "labeledRecordRate": round(records_with_labels / denominator, 6),
    }
    missing_level1 = [name for name in tree["level1"] if name not in level1_counts]
    missing_level2 = [name for name in tree["level2"] if name not in level2_counts]
    return {
        "status": "ok",
        "treeVersion": tree["treeVersion"],
        "definitions": "见 configs/profile.json domain.coverageDefinitions",
        "coverage": coverage,
        "labeledRecords": records_with_labels,
        "textRecords": text_records,
        "level1": {
            "total": len(tree["level1"]),
            "covered": len(level1_counts),
            "counts": dict(sorted(level1_counts.items(), key=lambda item: (-item[1], item[0]))),
            "missing": missing_level1,
        },
        "level2": {
            "total": len(tree["level2"]),
            "covered": len(level2_counts),
            "counts": dict(sorted(level2_counts.items(), key=lambda item: (-item[1], item[0]))),
            "missing": missing_level2[:200],
        },
        "leaves": {
            "total": len(tree["leaves"]),
            "covered": len(leaf_counts),
            "top": [
                {"path": key, "count": count}
                for key, count in sorted(leaf_counts.items(), key=lambda item: (-item[1], item[0]))[:50]
            ],
        },
        "gaps": {"level1": missing_level1, "level2Count": len(missing_level2)},
    }
