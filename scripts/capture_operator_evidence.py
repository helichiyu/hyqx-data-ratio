"""把一次算子运行目录整理为标准证据目录（9 件套 + 产物）。

用法：
    python scripts/capture_operator_evidence.py \
        --operator-dir dm-text-clustering \
        --run-dir operator/runtime/output/_dev_op03 \
        --operator-id dm-text-clustering \
        --command "..." --status "完成（本机真实产物）"

只复制本机真实运行产物；指标来自 metrics.json，未评测项保留 null。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_ROOT = ROOT / "operator"


def _environment() -> str:
    def version(module: str) -> str:
        try:
            imported = __import__(module)
            return str(getattr(imported, "__version__", "?"))
        except Exception:  # noqa: BLE001
            return "missing"

    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False)
    return "\n".join(
        [
            f"python: {sys.version.split()[0]}",
            f"platform: {platform.platform()}",
            f"torch: {version('torch')}",
            f"transformers: {version('transformers')}",
            f"funasr: {version('funasr')}",
            f"rapidocr: {version('rapidocr_onnxruntime')}",
            f"numpy: {version('numpy')}",
            f"ffmpeg: {(ffmpeg.stdout or ffmpeg.stderr or 'unavailable').splitlines()[0]}",
        ]
    )


def _report(operator_id: str, run_id: str, metrics: dict, command: str, status: str,
            notes: str) -> str:
    keys = [
        "sampleCount", "successCount", "failedCount", "labeledRate", "k", "silhouette",
        "vectorDimension", "modelVersion", "treeVersion", "labelSpaceSize",
        "labeledCounts", "unknownCounts", "illegalLabels", "legalRate",
        "annotation", "reviewMetrics", "unclassifiedByReason",
    ]
    rows = []
    for key in keys:
        if key in metrics:
            value = metrics[key]
            rows.append(f"| {key} | {json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value} |")
    table = "\n".join(rows)
    return f"""# 工作包回执 · {operator_id}

## 状态
{status}

## 变更文件
- 见 git 提交 `feat(s2)` 的 diff。

## 运行命令
```bash
{command}
```

## 证据路径
- 结果目录：`operator/{operator_id}/output/evidence/{run_id}/`
- 指标文件：`metrics.json`
- 日志：`logs/service.log`（直接调用 core.run，无 HTTP 服务日志）
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
{table}

- 效果指标（与人工标注比对）：`null`，`blockedReason=MATCHING_ANNOTATION_REQUIRED`（H-05）。
- 证据来自真实模型/真实样例；无随机数/常量伪造。

## 未决问题
- 阻塞项：无（本机链路）。
- 需人工确认：H-02 树版本、H-05 人工标注、H-06 模型许可与算力、Docker/容器探针（H-01）。
- 已知限制：{notes}

## 下一步
人工标注到位后补准确率/Wilson/混淆矩阵；阶段门禁复核。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="整理算子证据目录")
    parser.add_argument("--operator-dir", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--command", default="（未登记）")
    parser.add_argument("--status", default="完成（本机真实产物）")
    parser.add_argument("--notes", default="见 README 已知限制。")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    run_id = manifest["runId"]
    evidence = OPERATOR_ROOT / args.operator_dir / "output" / "evidence" / run_id
    if evidence.exists():
        shutil.rmtree(evidence)
    shutil.copytree(run_dir, evidence)

    input_manifest = evidence / "input_manifest.json"
    if input_manifest.is_file():
        shutil.copyfile(input_manifest, evidence / "input-manifest.json")
    (evidence / "logs").mkdir(exist_ok=True)
    (evidence / "logs" / "service.log").write_text(
        "直接调用 core.run，无 HTTP 服务；服务级证据见 docs/算子开发/evidence/S2/。\n",
        encoding="utf-8",
        newline="\n",
    )
    (evidence / "command.txt").write_text(args.command + "\n", encoding="utf-8", newline="\n")
    (evidence / "environment.txt").write_text(
        _environment() + "\n", encoding="utf-8", newline="\n"
    )
    metrics = json.loads((evidence / "metrics.json").read_text(encoding="utf-8"))
    (evidence / "report.md").write_text(
        _report(args.operator_id, run_id, metrics, args.command, args.status, args.notes),
        encoding="utf-8",
        newline="\n",
    )
    lines = []
    for path in sorted(evidence.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name == "artifacts.sha256":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(evidence).as_posix()}")
    (evidence / "artifacts.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    print(evidence.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
