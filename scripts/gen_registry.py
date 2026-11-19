"""由 operator/map.json 生成算子台账 docs/算子开发/registry.json（S0-6）。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/gen_registry.py

台账保留状态机字段（status/statusUpdatedAt/evidencePath），状态取值遵循任务书 9.1；
publishId 固定为 null：按已确认口径不生成对外发布 ID，operatorId 以目录名为准。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "operator" / "map.json"
OUTPUT = ROOT / "docs" / "算子开发" / "registry.json"
GENERATED_AT = "2026-11-16"

STATUS_NOT_STARTED = "未开始"


def main() -> int:
    payload = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    operators = payload["operators"]
    if not operators:
        raise SystemExit("map.json 没有任何算子")

    rows = []
    for meta in operators:
        rows.append(
            {
                "opId": meta["opId"],
                "operatorId": meta["operatorId"],
                "nameZh": meta["nameZh"],
                "semanticCode": meta["semanticCode"],
                "stage": meta["stage"],
                "priority": meta["priority"],
                "group": meta["group"],
                "dependsOn": list(meta.get("dependsOn") or []),
                "status": STATUS_NOT_STARTED,
                "statusUpdatedAt": GENERATED_AT,
                "evidencePath": None,
                "publishId": None,
                "note": "不生成对外发布 ID，operatorId 以目录名为准；S0 仅骨架，未开始算法实现。",
            }
        )

    registry = {
        "version": payload["version"],
        "generatedAt": GENERATED_AT,
        "generatedBy": "scripts/gen_registry.py",
        "source": "operator/map.json + docs/任务要求/算子清单 xlsx 01/03 表",
        "publishIdPolicy": "不生成对外发布 ID（已确认口径）；如需发布 ID 按《平台相关 ID 生成规范》另行申请。",
        "statusMachine": ["未开始", "进行中", "自测通过", "待评审", "已验收", "阻塞"],
        "operators": rows,
    }
    OUTPUT.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成 {OUTPUT.relative_to(ROOT)}（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
