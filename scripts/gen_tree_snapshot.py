"""把分类体系 xlsx 解析为 baseline/tree-snapshot.json（S0-5）。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/gen_tree_snapshot.py

输出带 treeVersion、源文件 SHA-256、节点 path/parent/depth/leaf，供 OP-05/OP-06/OP-08
读取。``treeVersion`` 在人工确认权威源前固定为 ``taxonomy-1013-pending``（H-02/Q-01）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "任务要求" / "【分类体系】分类体系结构-1013-zsy.xlsx"
OUTPUT = ROOT / "operator" / "baseline" / "tree-snapshot.json"
TREE_VERSION = "taxonomy-1013-pending"
GENERATED_AT = "2026-11-16"

TREE_SHEETS = {
    "content": "主线-内容（唯一）",
    "domain": "领域（多选）",
    "ability": "能力（多选）",
}


def _text(value: Any) -> str:
    return "" if value is None else " ".join(str(value).split())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_tree(worksheet: Any) -> dict[str, Any]:
    """解析一级/二级/三级列，向上填充合并单元格留下的空值。"""

    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_l1 = ""
    current_l2 = ""
    current_l1_desc = ""

    for row in worksheet.iter_rows(min_row=2, max_col=4, values_only=True):
        level1, description, level2, level3 = (_text(item) for item in row)
        if level1:
            current_l1 = level1
            current_l1_desc = description
            current_l2 = ""
        if level2:
            current_l2 = level2
        if not current_l1:
            continue

        def add(path: list[str], desc: str = "") -> None:
            key = "/".join(path)
            if key in seen:
                return
            seen.add(key)
            parent = "/".join(path[:-1]) if len(path) > 1 else None
            nodes.append(
                {
                    "nodeId": key,
                    "path": path,
                    "name": path[-1],
                    "depth": len(path),
                    "parentId": parent,
                    "leaf": True,
                    "description": desc or "",
                }
            )

        add([current_l1], current_l1_desc)
        if current_l2:
            add([current_l1, current_l2])
        if level3:
            if not current_l2:
                raise ValueError(f"{worksheet.title} 出现无二级的三级分类：{level3}")
            add([current_l1, current_l2, level3])

    # 有子节点的节点不是叶子
    parents = {node["parentId"] for node in nodes if node["parentId"]}
    for node in nodes:
        node["leaf"] = node["nodeId"] not in parents

    level_counts = {depth: sum(1 for node in nodes if node["depth"] == depth) for depth in (1, 2, 3)}
    return {
        "nodeCount": len(nodes),
        "levelCounts": {f"level{depth}": count for depth, count in level_counts.items()},
        "nodes": nodes,
    }


def _parse_overview(worksheet: Any) -> list[dict[str, Any]]:
    dimensions: list[dict[str, Any]] = []
    group = ""
    for row in worksheet.iter_rows(min_row=4, max_col=8, values_only=True):
        group_cell, dimension, selection, labeling, sheet, basis, example, note = (_text(item) for item in row)
        if group_cell:
            group = group_cell
        if not dimension:
            continue
        dimensions.append(
            {
                "group": group,
                "dimension": dimension,
                "selection": selection,
                "labeling": labeling,
                "sheet": sheet,
                "basis": basis,
                "example": example,
                "note": note,
            }
        )
    return dimensions


def _parse_extension_tags(worksheet: Any) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    group_name = ""
    dimension = ""
    selection = ""
    for row in worksheet.iter_rows(min_row=2, max_col=5, values_only=True):
        group_cell, dimension_cell, value, description, selection_cell = (_text(item) for item in row)
        if group_cell:
            group_name = group_cell
        if dimension_cell:
            dimension = dimension_cell
        if selection_cell:
            selection = selection_cell
        if not (dimension and value):
            continue
        bucket = groups.setdefault(
            f"{group_name}/{dimension}",
            {"group": group_name, "dimension": dimension, "selection": selection, "values": []},
        )
        bucket["values"].append({"value": value, "description": description})
    return groups


def main() -> int:
    if not SOURCE.is_file():
        print(f"源文件不存在：{SOURCE}")
        return 1
    workbook = openpyxl.load_workbook(SOURCE, data_only=True)
    missing = [sheet for sheet in TREE_SHEETS.values() if sheet not in workbook.sheetnames]
    if missing:
        print(f"缺少 sheet：{missing}")
        return 1

    trees = {key: _parse_tree(workbook[sheet]) for key, sheet in TREE_SHEETS.items()}
    snapshot = {
        "treeVersion": TREE_VERSION,
        "status": "pending-confirmation",
        "statusNote": "treeVersion 与权威源待人工确认（H-02/Q-01）；确认后升版本并保留本快照追溯。",
        "sourceFile": SOURCE.relative_to(ROOT).as_posix(),
        "sourceSha256": _sha256(SOURCE),
        "generatedAt": GENERATED_AT,
        "generatedBy": "scripts/gen_tree_snapshot.py",
        "dimensions": _parse_overview(workbook["分类体系总览"]),
        "trees": trees,
        "extensionTags": _parse_extension_tags(workbook["扩展与管控标签"]),
        "stats": {
            "content": trees["content"]["levelCounts"],
            "domain": trees["domain"]["levelCounts"],
            "ability": trees["ability"]["levelCounts"],
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成 {OUTPUT.relative_to(ROOT)}")
    for key, tree in trees.items():
        print(f"  {key}: {tree['nodeCount']} 节点 {tree['levelCounts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
