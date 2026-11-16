"""校验三份 JSON Schema 与正/反样例（S0-3）。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/validate_schemas.py

规则：
    samples/<schema>/valid-*.json    必须通过
    samples/<schema>/invalid-*.json  必须被拒绝
任一不符即退出码 1。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "docs" / "算子开发" / "schemas"
SCHEMAS = ("record", "manifest", "result")


def main() -> int:
    failures: list[str] = []
    for name in SCHEMAS:
        schema_path = SCHEMA_DIR / f"{name}.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        sample_dir = SCHEMA_DIR / "samples" / name
        valid_files = sorted(sample_dir.glob("valid-*.json"))
        invalid_files = sorted(sample_dir.glob("invalid-*.json"))
        if not valid_files or not invalid_files:
            failures.append(f"{name}: 缺少正/反样例")
            continue

        for path in valid_files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
            if errors:
                failures.append(f"{path.relative_to(ROOT)} 应通过却被拒：{errors[0].message}")
            else:
                print(f"  PASS  {path.relative_to(ROOT)}")

        for path in invalid_files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            errors = list(validator.iter_errors(payload))
            if not errors:
                failures.append(f"{path.relative_to(ROOT)} 应被拒却通过")
            else:
                print(f"  REJECT {path.relative_to(ROOT)} -> {errors[0].message}")

    if failures:
        print("\nSchema 校验失败：", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"\nSchema 校验通过：{len(SCHEMAS)} 份 schema，正样例全通过、反样例全拒绝")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
