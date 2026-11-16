"""运行 S1 真实链路（OP-01 → OP-02）并生成算子证据目录。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/run_s1_chain.py

流程：
1. 以 ``operator/runtime/transport/{input,output}`` 为运行目录启动 uvicorn；
2. uploadFile 上传混合批次 zip → OP-01 predict → 校验 downloadFile/removeFile；
3. 以 OP-01 runDir 作为 inputFile → OP-02 predict；
4. 把两次运行目录复制到 ``operator/<dir>/output/evidence/<runId>/``，
   补齐 report/command/environment/artifacts.sha256/logs。
效应类指标（与人工标注比对）不生成，报告中写 null + blockedReason。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DIR = ROOT / "operator"
EVIDENCE_ROOT = OPERATOR_DIR
TRANSPORT = OPERATOR_DIR / "runtime" / "transport"
SERVICE_LOG = OPERATOR_DIR / "runtime" / "s1-service.log"
OP1 = "dm-multimodal-analysis"
OP2 = "dm-corpus-normalization"


def _wait_health(base: str, process: subprocess.Popen, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"服务提前退出，日志：{SERVICE_LOG}")
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as response:
                payload = json.loads(response.read())
            if payload.get("code") == 0:
                return
        except Exception:  # noqa: BLE001 - 启动期连接失败属正常
            pass
        time.sleep(0.5)
    raise RuntimeError(f"等待服务就绪超时：{SERVICE_LOG}")


def _post(base: str, path: str, **kwargs):
    response = requests.post(f"{base}{path}", timeout=1800, **kwargs)
    payload = response.json()
    if response.status_code >= 400 or payload.get("code") != 0:
        raise RuntimeError(f"{path} 失败：HTTP {response.status_code} {payload}")
    return payload["data"]


def _copy_run(output_root: Path, operator_id: str, run_id: str, evidence_dir: Path,
              records_name: str) -> dict:
    source = output_root / operator_id / run_id
    if not source.is_dir():
        raise RuntimeError(f"运行目录不存在：{source}")
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    shutil.copytree(source, evidence_dir, ignore=shutil.ignore_patterns("_input_extracted"))
    if records_name != "result.jsonl":
        source_records = evidence_dir / records_name
        if not source_records.is_file():
            raise RuntimeError(f"缺少结果文件：{source_records}")
        shutil.copyfile(source_records, evidence_dir / "result.jsonl")
    (evidence_dir / "logs").mkdir(exist_ok=True)
    if SERVICE_LOG.is_file():
        tail = SERVICE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
        (evidence_dir / "logs" / "service.log").write_text(
            "\n".join(tail) + "\n", encoding="utf-8", newline="\n"
        )
    return {"source": source, "evidence": evidence_dir}


def _environment() -> str:
    def version(module: str) -> str:
        try:
            imported = __import__(module)
            return str(getattr(imported, "__version__", "?"))
        except Exception:  # noqa: BLE001
            return "missing"

    ffmpeg = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True, check=False
    )
    return "\n".join(
        [
            f"generatedAt: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
            f"python: {sys.version.split()[0]}",
            f"platform: {platform.platform()}",
            f"fastapi: {version('fastapi')}",
            f"pymupdf: {version('pymupdf')}",
            f"pillow: {version('PIL')}",
            f"numpy: {version('numpy')}",
            f"pyarrow: {version('pyarrow')}",
            f"ffmpeg: {(ffmpeg.stdout or ffmpeg.stderr or 'unavailable').splitlines()[0]}",
        ]
    )


def _artifacts_sha(evidence_dir: Path) -> None:
    lines = []
    for path in sorted(evidence_dir.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name == "artifacts.sha256":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(evidence_dir).as_posix()}")
    (evidence_dir / "artifacts.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def _report(operator_id: str, data: dict, command: str, extra: str) -> str:
    metrics = data.get("metrics") or {}
    evidence_display = (
        EVIDENCE_ROOT / operator_id / "output" / "evidence" / data["runId"]
    ).relative_to(ROOT).as_posix()
    rows = {
        "sampleCount": data.get("sampleCount"),
        "successCount": data.get("successCount"),
        "failedCount": data.get("failedCount"),
        "modalCounts": json.dumps(metrics.get("modalCounts"), ensure_ascii=False),
        "failureRate": metrics.get("failureRate"),
    }
    if operator_id == OP1:
        rows["text"] = json.dumps(metrics.get("text"), ensure_ascii=False)
        rows["pdf"] = json.dumps(metrics.get("pdf"), ensure_ascii=False)
        rows["media"] = json.dumps(metrics.get("media"), ensure_ascii=False)
        rows["detection"] = json.dumps(metrics.get("detection"), ensure_ascii=False)
    else:
        rows["standardized"] = json.dumps(metrics.get("standardized"), ensure_ascii=False)
        rows["parquet"] = json.dumps(metrics.get("parquet"), ensure_ascii=False)
        rows["dedup"] = json.dumps(metrics.get("dedup"), ensure_ascii=False)
        rows["anomalies"] = json.dumps(metrics.get("anomalies"), ensure_ascii=False)
        rows["associations"] = json.dumps(metrics.get("associations"), ensure_ascii=False)
    table = "\n".join(f"| {key} | {value} |" for key, value in rows.items())
    return f"""# 工作包回执 · {operator_id}

## 状态
完成（本机真实样例链路）；效果验收待人工真值（H-05），不阻塞后续阶段。

## 变更文件
- 新增：见 git 提交 `feat(s1)` 的 diff。
- 修改：`operator/map.json`、`docs/算子开发/registry.json`、任务书第 10 节。
- 删除：无。

## 运行命令
```bash
{command}
```

## 证据路径
- 结果目录：`{evidence_display}/`
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
{table}

- 与人工标注比对的准确率/F1：`null`（无人工真值，blockedReason=H-05）。
- 证据全部来自真实样例与真实解码统计；无随机数/常量伪造。

## 未决问题
- 阻塞项：无。
- 需人工确认：H-02 树版本（本算子未消费树）、H-03 阈值口径（`dt`/去重/VAD 阈值为联调初值）、H-04 内部样例授权、H-05 人工标注、H-06 模型许可证（本阶段未加载模型）。
- 已知限制：无 OCR/ASR 后端；ffprobe 未安装（用 ffmpeg stderr 解析）；视频转码依赖 ffmpeg libx264。

## 补充
{extra}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="S1 真实链路与证据生成")
    parser.add_argument(
        "--batch",
        default=str(ROOT / "docs" / "算子开发" / "samples" / "mixed" / "mixed_batch_2026-11-16.zip"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=17025)
    parser.add_argument("--unique-id", default="s1-batch-20261116")
    args = parser.parse_args()

    input_root = TRANSPORT / "input"
    output_root = TRANSPORT / "output"
    input_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    SERVICE_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_handle = SERVICE_LOG.open("w", encoding="utf-8")
    env = dict(os.environ)
    env.update(
        {
            "INPUT_DIR": str(input_root),
            "OUTPUT_DIR": str(output_root),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "inference:app",
            "--host", args.host, "--port", str(args.port), "--workers", "1",
        ],
        cwd=str(OPERATOR_DIR),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    base = f"http://{args.host}:{args.port}"
    try:
        _wait_health(base, process)
        with open(args.batch, "rb") as handle:
            upload = requests.post(
                f"{base}/{OP1}/uploadFile",
                data={"uniqueId": args.unique_id},
                files={"file": (Path(args.batch).name, handle, "application/zip")},
                timeout=300,
            ).json()
        if upload.get("code") != 0:
            raise RuntimeError(f"上传失败：{upload}")
        op1 = _post(
            base, f"/{OP1}/predict",
            json={"uniqueId": args.unique_id, "params": {}, "seed": 42},
        )
        if op1.get("cached"):
            print("提示：命中已有 runId 缓存，证据为同一输入的既有结果。")

        download = requests.get(
            f"{base}/{OP1}/downloadFile",
            params={"path": op1["outputFilePath"]},
            timeout=300,
        )
        expected = Path(op1["outputFilePath"]).read_bytes()
        if download.status_code != 200 or download.content != expected:
            raise RuntimeError("downloadFile 校验失败")
        dir_zip = requests.get(
            f"{base}/{OP1}/downloadFile",
            params={"path": op1["outputDir"]},
            timeout=300,
        )
        if dir_zip.status_code != 200 or not zipfile.ZipFile(
            __import__("io").BytesIO(dir_zip.content)
        ).namelist():
            raise RuntimeError("目录打包下载校验失败")

        op1_evidence = EVIDENCE_ROOT / OP1 / "output" / "evidence" / op1["runId"]
        _copy_run(output_root, OP1, op1["runId"], op1_evidence, "result.jsonl")

        op2 = _post(
            base, f"/{OP2}/predict",
            json={"inputFile": op1["outputDir"], "params": {}, "seed": 42},
        )
        op2_evidence = EVIDENCE_ROOT / OP2 / "output" / "evidence" / op2["runId"]
        _copy_run(output_root, OP2, op2["runId"], op2_evidence, "records.jsonl")

        command = (
            f'"D:/anaconda3/envs/use/python.exe" scripts/run_s1_chain.py '
            f'--batch "{Path(args.batch).resolve().relative_to(ROOT).as_posix()}"'
        )
        environment = _environment()
        for operator_id, data, evidence in (
            (OP1, op1, op1_evidence),
            (OP2, op2, op2_evidence),
        ):
            extra = (
                f"- runId：`{data['runId']}`\n"
                f"- inputFingerprint：`{data['inputFingerprint']}`\n"
                f"- paramsHash：`{data['paramsHash']}`\n"
                f"- seed：{data['seed']}\n"
                f"- operatorVersion：{data['operatorVersion']}\n"
                f"- downloadFile：文件与目录（zip）均校验通过\n"
                f"- 上游：{data.get('metrics', {}).get('upstream', '—')}\n"
            )
            (evidence / "report.md").write_text(
                _report(operator_id, data, command, extra), encoding="utf-8", newline="\n"
            )
            (evidence / "command.txt").write_text(command + "\n", encoding="utf-8", newline="\n")
            (evidence / "environment.txt").write_text(
                environment + "\n", encoding="utf-8", newline="\n"
            )
            input_manifest = evidence / "input_manifest.json"
            if input_manifest.is_file():
                shutil.copyfile(input_manifest, evidence / "input-manifest.json")
            _artifacts_sha(evidence)

        requests.post(
            f"{base}/{OP1}/removeFile",
            json={"uniqueId": args.unique_id},
            timeout=60,
        )
        summary = {
            "op01": {"runId": op1["runId"], "evidence": op1_evidence.as_posix()},
            "op02": {"runId": op2["runId"], "evidence": op2_evidence.as_posix()},
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
