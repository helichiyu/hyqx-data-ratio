"""为 map.json 中的算子生成同名包骨架（幂等，不覆盖已有文件）。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/scaffold_operators.py

生成结构（package 名 = 目录名，含连字符，包内只用相对导入）：

    operator/_template/
        __init__.py  core.py  configs/.gitkeep  utils/__init__.py
    operator/dm-xxx/
        __init__.py  core.py  configs/.gitkeep  utils/__init__.py

权重统一放 operator/weights/：共享模型放 shared/，单算子私有放 <operatorId>/；
算子目录内不再建 weight/，避免同一模型重复打包。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "map.json"
OPERATOR_ROOT = ROOT / "operator"

CORE_TEMPLATE = '''"""算子核心入口（S0 骨架）。

约定：``core.run(input_path, params, seed, output_dir) -> dict``；
本文件不依赖 FastAPI/HTTP，HTTP 层由仓库根 ``inference.py`` 统一实现。
S0 阶段只声明未实现，不伪造任何计算结果。
"""

from __future__ import annotations

OPERATOR_VERSION = "0.1.0"
REASON_NOT_IMPLEMENTED = "OPERATOR_NOT_IMPLEMENTED"


def run(input_path: str, params: dict | None = None, seed: int | None = None,
        output_dir: str | None = None) -> dict:
    """执行算子计算；S0 阶段只声明未实现，不伪造结果。"""
    raise NotImplementedError(REASON_NOT_IMPLEMENTED)
'''

INIT_TEMPLATE = '''"""算子包（S0 骨架）：包名与目录名一致，内部使用相对导入。"""
'''


def _write_if_absent(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def scaffold_package(package_dir: Path, package_name: str) -> list[str]:
    """生成一个包骨架，返回本次新建的相对路径列表。"""

    created: list[str] = []
    if _write_if_absent(package_dir / "__init__.py", INIT_TEMPLATE):
        created.append(f"{package_name}/__init__.py")
    if _write_if_absent(package_dir / "core.py", CORE_TEMPLATE):
        created.append(f"{package_name}/core.py")
    if _touch_if_absent(package_dir / "configs" / ".gitkeep"):
        created.append(f"{package_name}/configs/.gitkeep")
    if _write_if_absent(package_dir / "utils" / "__init__.py", INIT_TEMPLATE):
        created.append(f"{package_name}/utils/__init__.py")
    return created


def main() -> int:
    registry = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    operators = registry["operators"]
    if len(operators) != 22:
        print(f"map.json 应有 22 个算子，实际 {len(operators)} 个", file=sys.stderr)
        return 1

    created: list[str] = scaffold_package(OPERATOR_ROOT / "_template", "_template")
    for meta in operators:
        operator_id = meta["operatorId"]
        created.extend(scaffold_package(OPERATOR_ROOT / operator_id, operator_id))

    print(f"scaffold 完成：22 个算子 + _template，本次新建 {len(created)} 个文件")
    for item in created:
        print(f"  + {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
