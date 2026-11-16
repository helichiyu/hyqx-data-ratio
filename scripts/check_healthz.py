"""逐个调用 22 个算子的 healthz（S0-1 / S0-8）。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/check_healthz.py --base-url http://127.0.0.1:17025

退出码 0 表示 22/22 返回 ``code=0`` 且 ``data.ready=true``。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = ROOT / "operator" / "map.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="检查算子 healthz")
    parser.add_argument("--base-url", default="http://127.0.0.1:17025")
    parser.add_argument("--map", default=str(DEFAULT_MAP))
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    operators = json.loads(Path(args.map).read_text(encoding="utf-8"))["operators"]
    base = args.base_url.rstrip("/")
    failures: list[str] = []

    aggregate_url = f"{base}/health"
    try:
        with urllib.request.urlopen(aggregate_url, timeout=args.timeout) as response:
            aggregate = json.loads(response.read().decode("utf-8"))
        print(f"AGG  {aggregate_url}  code={aggregate.get('code')}  {aggregate.get('data')}")
        if aggregate.get("code") != 0:
            failures.append(f"{aggregate_url} 返回 code={aggregate.get('code')}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        failures.append(f"{aggregate_url} 不可达：{exc}")

    for operator in operators:
        operator_id = operator["operatorId"]
        url = f"{base}/{operator_id}/healthz"
        try:
            with urllib.request.urlopen(url, timeout=args.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures.append(f"{operator_id}: {exc}")
            print(f"FAIL {url}  {exc}")
            continue
        data = payload.get("data") or {}
        ok = payload.get("code") == 0 and data.get("ready") is True
        marker = "OK  " if ok else "FAIL"
        print(
            f"{marker} {url}  ready={data.get('ready')}  weightsOk={data.get('weightsOk')}  "
            f"deps={data.get('dependencyStatus')}"
        )
        if not ok:
            failures.append(f"{operator_id}: code={payload.get('code')} ready={data.get('ready')}")

    if failures:
        print("\nhealthz 检查失败：", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"\nhealthz 检查通过：{len(operators)}/{len(operators)} 个算子 ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
