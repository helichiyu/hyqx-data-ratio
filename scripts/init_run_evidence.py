"""生成一次运行证据目录的 9 件文件（S0-4）。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/init_run_evidence.py \
        --output-dir docs/算子开发/evidence/S0-1/run-20261116 \
        --operator-id dm-multimodal-analysis

生成（已存在文件默认跳过，避免覆盖历史证据）：
    report.md  command.txt  environment.txt  input-manifest.json
    result.jsonl  result.json  metrics.json  failures.jsonl  artifacts.sha256  logs/

指标未评测时写 `null` + `blockedReason`，不编造。
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPORT_TEMPLATE = """# 工作包回执 · {operator_id}

## 状态
未填写（完成 / 部分完成 / 阻塞三选一）

## 变更文件
- 新增：
- 修改：
- 删除：

## 运行命令
```bash
{command}
```

## 证据路径
- 结果目录：{output_dir}
- 指标文件：metrics.json
- 日志：logs/
- 样例输入：input-manifest.json

## 指标
| 指标 | 值 | 样本量 | 置信区间/口径 | 证据 |
| --- | --- | --- | --- | --- |
| — | null | 0 | 未评测，见 blockedReason | — |

## 未决问题
- 阻塞项：
- 需人工确认：
- 已知限制：

## 下一步
"""


def _command_version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        first = (result.stdout or result.stderr or "").strip().splitlines()
        return first[0] if first else "unavailable"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _write_if_absent(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 9 件运行证据文件")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--operator-id", default="op-data-mixing")
    parser.add_argument("--command", default="（未登记）")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("run-%Y%m%dT%H%M%S")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logs").mkdir(exist_ok=True)
    (output_dir / "logs" / ".gitkeep").touch()

    environment = "\n".join(
        [
            f"generatedAt: {datetime.now().isoformat(timespec='seconds')}",
            f"runId: {run_id}",
            f"operatorId: {args.operator_id}",
            f"python: {sys.version.split()[0]}",
            f"platform: {platform.platform()}",
            f"ffmpeg: {_command_version(['ffmpeg', '-version'])}",
            f"docker: {_command_version(['docker', '--version'])}",
            f"dockerCompose: {_command_version(['docker', 'compose', 'version'])}",
        ]
    )

    created = []
    if _write_if_absent(
        output_dir / "report.md",
        REPORT_TEMPLATE.format(
            operator_id=args.operator_id,
            command=args.command,
            output_dir=output_dir.as_posix(),
        ),
    ):
        created.append("report.md")
    if _write_if_absent(output_dir / "command.txt", f"{args.command}\n"):
        created.append("command.txt")
    if _write_if_absent(output_dir / "environment.txt", environment + "\n"):
        created.append("environment.txt")
    if _write_if_absent(
        output_dir / "input-manifest.json",
        json.dumps(
            {
                "runId": run_id,
                "inputFingerprint": None,
                "files": [],
                "note": "运行前填写输入文件清单、大小与 SHA-256。",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    ):
        created.append("input-manifest.json")
    if _write_if_absent(output_dir / "result.jsonl", ""):
        created.append("result.jsonl")
    if _write_if_absent(
        output_dir / "result.json",
        json.dumps({"code": None, "msg": "未运行", "data": {}}, ensure_ascii=False, indent=2) + "\n",
    ):
        created.append("result.json")
    if _write_if_absent(
        output_dir / "metrics.json",
        json.dumps(
            {"metrics": {}, "blockedReason": "not_evaluated", "note": "无真值/未评测时不得编造指标。"},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    ):
        created.append("metrics.json")
    if _write_if_absent(output_dir / "failures.jsonl", ""):
        created.append("failures.jsonl")
    if _write_if_absent(output_dir / "artifacts.sha256", ""):
        created.append("artifacts.sha256")

    print(f"证据目录：{output_dir}")
    print(f"本次新建 {len(created)} 个文件：{', '.join(created) if created else '无（已存在，未覆盖）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
