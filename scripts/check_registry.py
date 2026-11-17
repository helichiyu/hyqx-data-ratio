"""比对算子清单 xlsx、operator/map.json 与 registry.json（S0-6）。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/check_registry.py

检查项：
1. 三处均 22 行，opId/operatorId 唯一；
2. xlsx 01 表与 map.json 的 opId / operatorId / 名称 / 优先级 / 大环节逐行一致；
3. map.json 与 registry.json 的全部登记字段一致；
4. 依赖引用存在、无自依赖、无环；
5. status 取值合法，publishId 为 null。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "docs" / "算子开发" / "【算子清单】数据配比中心算子开发清单_2026-11-16.xlsx"
MAP_PATH = ROOT / "operator" / "map.json"
REGISTRY_PATH = ROOT / "docs" / "算子开发" / "registry.json"

STATUS_SET = {"未开始", "进行中", "自测通过", "待评审", "已验收", "阻塞"}
COMPARE_FIELDS = ("opId", "operatorId", "nameZh", "priority", "group")
REGISTRY_FIELDS = (
    "opId", "operatorId", "nameZh", "semanticCode", "stage", "priority", "group", "dependsOn",
)


def _text(value) -> str:
    return "" if value is None else " ".join(str(value).split())


def load_xlsx_rows() -> list[dict[str, str]]:
    workbook = openpyxl.load_workbook(XLSX, data_only=True)
    sheet = workbook["01-算子总表"]
    header = [_text(cell) for cell in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True))]
    index = {name: position for position, name in enumerate(header)}
    rows = []
    for values in sheet.iter_rows(min_row=2, values_only=True):
        op_id = _text(values[index["算子ID"]])
        if not op_id:
            continue
        rows.append(
            {
                "opId": op_id,
                "operatorId": _text(values[index["算子英文名"]]),
                "nameZh": _text(values[index["算子名称"]]),
                "priority": _text(values[index["优先级"]]),
                "group": _text(values[index["大环节"]]),
            }
        )
    return rows


def main() -> int:
    problems: list[str] = []
    map_payload = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    registry_payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    map_rows = map_payload["operators"]
    registry_rows = registry_payload["operators"]
    xlsx_rows = load_xlsx_rows()

    for label, rows in (("map.json", map_rows), ("registry.json", registry_rows), ("xlsx", xlsx_rows)):
        if len(rows) != 22:
            problems.append(f"{label} 应为 22 行，实际 {len(rows)} 行")
        op_ids = [row["opId"] for row in rows]
        operator_ids = [row["operatorId"] for row in rows]
        if len(set(op_ids)) != len(op_ids):
            problems.append(f"{label} 存在重复 opId")
        if len(set(operator_ids)) != len(operator_ids):
            problems.append(f"{label} 存在重复 operatorId")

    xlsx_by_op = {row["opId"]: row for row in xlsx_rows}
    map_by_op = {row["opId"]: row for row in map_rows}
    registry_by_op = {row["opId"]: row for row in registry_rows}

    for op_id in sorted(set(map_by_op) | set(xlsx_by_op)):
        xlsx_row = xlsx_by_op.get(op_id)
        map_row = map_by_op.get(op_id)
        if xlsx_row is None or map_row is None:
            problems.append(f"{op_id} 在 xlsx 或 map.json 中缺失")
            continue
        for field in COMPARE_FIELDS:
            if xlsx_row[field] != map_row[field]:
                problems.append(
                    f"{op_id}.{field} 不一致：xlsx={xlsx_row[field]!r} map={map_row[field]!r}"
                )

    for op_id, map_row in map_by_op.items():
        registry_row = registry_by_op.get(op_id)
        if registry_row is None:
            problems.append(f"{op_id} 在 registry.json 中缺失")
            continue
        for field in REGISTRY_FIELDS:
            map_value = map_row.get(field)
            registry_value = registry_row.get(field)
            if isinstance(map_value, list):
                map_value = list(map_value)
                registry_value = list(registry_value or [])
            if map_value != registry_value:
                problems.append(
                    f"{op_id}.{field} map/registry 不一致：map={map_value!r} registry={registry_value!r}"
                )
        if registry_row.get("status") not in STATUS_SET:
            problems.append(f"{op_id}.status 非法：{registry_row.get('status')!r}")
        if registry_row.get("publishId") is not None:
            problems.append(f"{op_id}.publishId 应为 null")
        if registry_row.get("status") == "已验收":
            problems.append(f"{op_id} 不应由脚本标记已验收")
        map_status = map_row.get("status")
        registry_status = registry_row.get("status")
        if map_status == "scaffold" and registry_status not in {"未开始", "阻塞"}:
            problems.append(f"{op_id} map=scaffold 但 registry={registry_status!r}")
        if map_status == "implemented" and registry_status in {"未开始", "阻塞"}:
            problems.append(f"{op_id} map=implemented 但 registry={registry_status!r}")
        evidence_path = registry_row.get("evidencePath")
        if evidence_path:
            evidence_dir = ROOT / evidence_path.rstrip("/")
            if not evidence_dir.is_dir():
                problems.append(f"{op_id}.evidencePath 不存在：{evidence_path}")
        elif registry_status not in {"未开始", "阻塞"}:
            problems.append(f"{op_id} status={registry_status!r} 但 evidencePath 为空")

    known = set(map_by_op)
    for op_id, map_row in map_by_op.items():
        for dependency in map_row.get("dependsOn") or []:
            if dependency == op_id:
                problems.append(f"{op_id} 依赖自身")
            elif dependency not in known:
                problems.append(f"{op_id} 依赖不存在：{dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            problems.append("依赖存在环：" + " -> ".join(trail + [node]))
            return
        visiting.add(node)
        for dependency in map_by_op.get(node, {}).get("dependsOn") or []:
            visit(dependency, trail + [node])
        visiting.remove(node)
        visited.add(node)

    for op_id in map_by_op:
        visit(op_id, [])

    if problems:
        print("算子台账校验失败：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("算子台账校验通过：xlsx / map.json / registry.json 各 22 行一致，依赖无环，状态合法")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
