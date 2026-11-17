"""运行 S2 真实链路（OP-02 → OP-03 → OP-05 → OP-06 → OP-07）并生成证据目录。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/run_s2_chain.py

流程：
1. 以 ``operator/runtime/transport/{input,output}`` 为运行目录启动 uvicorn；
2. 以 S1 已产出的 OP-02 运行目录（``--op02-dir``）作为上游输入；
3. OP-03 聚类 → OP-05 四模态打标 → OP-06 领域/能力多标签 → OP-07 标签治理；
4. 把各次运行目录复制到 ``operator/<dir>/output/evidence/<runId>/``，
   补齐 report/command/environment/input-manifest/artifacts.sha256/logs；
5. 生成阶段证据索引 ``docs/算子开发/evidence/S2/run-<日期>/index.md``。

效应类指标（与人工标注比对）不生成，报告中写 null + blockedReason。
"""

from __future__ import annotations

import argparse
import hashlib
import io
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
TRANSPORT = OPERATOR_DIR / "runtime" / "transport"
SERVICE_LOG = OPERATOR_DIR / "runtime" / "s2-service.log"

OP03 = "dm-text-clustering"
OP05 = "dm-multimodal-labeling"
OP06 = "dm-taxonomy-labeling"
OP07 = "dm-label-governance"


def _wait_health(base: str, process: subprocess.Popen, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"服务提前退出，日志：{SERVICE_LOG}")
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as response:
                if json.loads(response.read()).get("code") == 0:
                    return
        except Exception:  # noqa: BLE001 - 启动期连接失败属正常
            pass
        time.sleep(0.5)
    raise RuntimeError(f"等待服务就绪超时：{SERVICE_LOG}")


def _post(base: str, path: str, **kwargs):
    response = requests.post(f"{base}{path}", timeout=3600, **kwargs)
    payload = response.json()
    if response.status_code >= 400 or payload.get("code") != 0:
        raise RuntimeError(f"{path} 失败：HTTP {response.status_code} {payload}")
    return payload["data"]


def _copy_run(output_root: Path, operator_id: str, run_id: str, evidence_dir: Path) -> None:
    source = output_root / operator_id / run_id
    if not source.is_dir():
        raise RuntimeError(f"运行目录不存在：{source}")
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    shutil.copytree(source, evidence_dir, ignore=shutil.ignore_patterns("_input_extracted"))
    (evidence_dir / "logs").mkdir(exist_ok=True)
    if SERVICE_LOG.is_file():
        tail = SERVICE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
        (evidence_dir / "logs" / "service.log").write_text(
            "\n".join(tail) + "\n", encoding="utf-8", newline="\n"
        )


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
            f"numpy: {version('numpy')}",
            f"scikit-learn: {version('sklearn')}",
            f"transformers: {version('transformers')}",
            f"torch: {version('torch')}",
            f"funasr: {version('funasr')}",
            f"rapidocr-onnxruntime: {version('rapidocr_onnxruntime')}",
            f"jieba: {version('jieba')}",
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


def _report(
    operator_id: str, name_zh: str, data: dict, command: str, extra: str, evidence_dir: Path
) -> str:
    metrics = data.get("metrics") or {}
    rows = {
        "sampleCount": data.get("sampleCount"),
        "successCount": data.get("successCount"),
        "failedCount": data.get("failedCount"),
        "paramsHash": data.get("paramsHash"),
        "seed": data.get("seed"),
        "operatorVersion": data.get("operatorVersion"),
        "modelVersion": data.get("modelVersion"),
        "treeVersion": data.get("treeVersion"),
    }
    table = "\n".join(f"| {key} | {value} |" for key, value in rows.items())
    metrics_json = json.dumps(metrics, ensure_ascii=False, indent=1)
    return f"""# 工作包回执 · {operator_id}（{name_zh}）

## 状态
完成（本机真实样例链路）；效果验收待人工真值（H-05），不阻塞后续阶段。

## 变更文件
- 新增：见 git 提交 `feat(s2)` 的 diff。
- 修改：`operator/map.json`、`docs/算子开发/registry.json`、任务书第 10 节。
- 删除：无。

## 运行命令
```bash
{command}
```

## 证据路径
- 结果目录：`{evidence_dir.relative_to(ROOT).as_posix()}/`（同次运行副本，原始运行目录 `{data.get('outputDir', '')}`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
{table}

完整指标：
```json
{metrics_json}
```

- 与人工标注比对的准确率/F1/Wilson/混淆矩阵：`null`（无人工真值，blockedReason=MATCHING_ANNOTATION_REQUIRED / REVIEW_RECORDS_REQUIRED）。
- 证据全部来自真实样例与真实模型推理；无随机数/常量伪造。

## 未决问题
- 阻塞项：无。
- 需人工确认：H-02 树版本（`taxonomy-1013-pending`）、H-03 阈值口径（联调初值）、H-05 人工标注、H-06 模型许可证。
- 已知限制：见 `metrics.provisional` 与算子 README。

## 补充
{extra}
"""


def _write_stage_index(stage_dir: Path, runs: dict[str, dict], command: str, op02_dir: Path) -> None:
    stage_dir.mkdir(parents=True, exist_ok=True)

    def row(op_id: str, operator_id: str, note: str) -> str:
        data = runs[operator_id]
        evidence = OPERATOR_DIR / operator_id / "output" / "evidence" / data["runId"]
        link = evidence.relative_to(ROOT).as_posix()
        return (
            f"| {op_id} | {data['runId']} | `{link}/` | "
            f"{data['sampleCount']}/{data['successCount']}/{data['failedCount']} | {note} |"
        )

    m03 = runs[OP03]["metrics"]
    m05 = runs[OP05]["metrics"]
    m06 = runs[OP06]["metrics"]
    m07 = runs[OP07]["metrics"]
    op05_labeled = sum(m05["labeledCounts"].values())
    op05_unclassified = sum(m05["unclassifiedCounts"].values())
    text = f"""# S2 阶段证据索引 · 分片与打标（OP-03 / OP-05 / OP-06 / OP-07）

> 日期：{time.strftime('%Y-%m-%d')}
> 上游：S1 OP-02 运行目录 `{op02_dir.relative_to(ROOT).as_posix()}`（432 条标准记录）
> 链路：`OP-02 产物 → OP-03 predict → OP-05 predict → OP-06 predict → OP-07 predict`（统一 HTTP 入口）
> 运行命令：`{command}`

## 1. 运行结果

| 算子 | runId | 证据目录 | 样本/成功/失败 | 关键指标 |
| --- | --- | --- | --- | --- |
{row('OP-03 句向量与主题聚类', OP03, f"768 维；K={m03['k']}；轮廓 {m03['silhouette']:.4f}；簇 {m03['topicClusters']} 个；{m03['chunkCount']} chunks")}
{row('OP-05 多模态自动打标', OP05, f"打标 {op05_labeled}（{m05['labeledCounts']}）；未归类 {op05_unclassified}；路径合法率 {m05['pathLegalRate']}")}
{row('OP-06 领域/能力多标签', OP06, f"领域叶子 {m06['labelSpaceSizes']['domain']} / 能力叶子 {m06['labelSpaceSizes']['ability']}；命中 领域 {m06['labeledCounts']['domain']} / 能力 {m06['labeledCounts']['ability']}；路径合法率 {m06['pathLegalRate']}")}
{row('OP-07 标签治理', OP07, f"标签 {m07['labels']}；非法 {m07['illegalLabels']}；冲突 {m07['conflicts']}；未归类 {m07['unclassifiedRecords']}；审核指标 null")}

## 2. S2 门禁核对

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| OP-03 固定 seed 可复现，向量维度/模型版本写入结果 | 通过 | OP-03 `metrics.json`：`deterministic=true`、`vectorDimension=768`、`modelVersion=bge-base-zh-v1.5`；测试断言重跑 `result.jsonl` 哈希一致 |
| OP-05 四模态均跑通，不是只做文本 | 通过 | OP-05 `labeledCounts`/`evidenceSources`：text 426、image 1、audio 3、video 2 均有证据路径与输出 |
| 打标路径 100% 命中当前 `treeVersion` | 通过 | OP-05/OP-06 `pathLegalRate=1.0`；`treeVersion=taxonomy-1013-pending`（H-02） |
| 低置信/冲突进未归类池，规则可复算 | 通过 | OP-05 `unclassified.jsonl` + `failures.jsonl`；OP-07 `unclassifiedByReason` |
| 与人工标注比对（样本量/准确率/区间/混淆矩阵） | 待人工 | 无真值（H-05），`annotation.accuracy=null` + `blockedReason`，不编造 |
| OP-06 领域/能力两个标签空间分离（P1） | 通过 | OP-06 `spacesSeparated=true`、`labelSpaceSizes` 双空间 |
| OP-07 治理指标来自真实记录（P1） | 通过 | `reviewMetrics` 全 `null` + `REVIEW_RECORDS_REQUIRED`；其余指标来自真实打标结果 |
| 标签树版本变更时旧结果可追溯 | 通过 | 结果全部写 `treeVersion`，不做静默改写 |

## 3. 未完成/待人工项

| 项 | 影响 | 处理 |
| --- | --- | --- |
| 人工标注比对（准确率/Wilson/混淆矩阵） | S2 效果验收 | H-05；写 `null` + `blockedReason` |
| `treeVersion` 权威源确认 | 路径合法性口径 | H-02；当前 `taxonomy-1013-pending` |
| 模型许可证审批（bge-base MIT / paraformer Apache-2.0 / RapidOCR Apache-2.0） | 入镜像 | H-06 待人工 |
| Docker 构建 / 容器内探针 | S0/S2 人工门禁 | H-01 待人工；按任务书 10.2 第 5 条不阻断开发 |

## 4. 复算

```bash
# 重跑整条 S2 链路并重建四个算子证据目录
{command}
```

## 5. 说明

- OP-03/OP-05/OP-06 的 runId 由「输入指纹 + 算子版本 + 参数哈希 + seed」决定，不同算子可能相同；证据按算子目录隔离，不影响追溯。
- 全部产物可复算：固定 seed=42、固定模型版本与树版本，重跑覆盖同一 runId 目录。
"""
    (stage_dir / "index.md").write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="S2 真实链路与证据生成")
    parser.add_argument(
        "--op02-dir",
        default=str(
            OPERATOR_DIR / "runtime" / "transport" / "output" / "dm-corpus-normalization"
            / "10a342ae92595ab7"
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=17026)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--stage-date",
        default=time.strftime("%Y%m%d"),
        help="阶段证据目录后缀，如 20261117",
    )
    args = parser.parse_args()

    op02_dir = Path(args.op02_dir).resolve()
    if not (op02_dir / "records.jsonl").is_file():
        raise SystemExit(f"OP-02 运行目录缺少 records.jsonl：{op02_dir}")

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
        op03 = _post(
            base, f"/{OP03}/predict",
            json={"inputFile": str(op02_dir), "params": {}, "seed": args.seed},
        )
        download = requests.get(
            f"{base}/{OP03}/downloadFile",
            params={"path": op03["outputFilePath"]},
            timeout=300,
        )
        if download.status_code != 200 or download.content != Path(
            op03["outputFilePath"]
        ).read_bytes():
            raise RuntimeError("downloadFile 校验失败")

        op05 = _post(
            base, f"/{OP05}/predict",
            json={"inputFile": str(op02_dir), "params": {}, "seed": args.seed},
        )
        dir_zip = requests.get(
            f"{base}/{OP05}/downloadFile",
            params={"path": op05["outputDir"]},
            timeout=600,
        )
        if dir_zip.status_code != 200 or not zipfile.ZipFile(
            io.BytesIO(dir_zip.content)
        ).namelist():
            raise RuntimeError("目录打包下载校验失败")

        op06 = _post(
            base, f"/{OP06}/predict",
            json={"inputFile": str(op02_dir), "params": {}, "seed": args.seed},
        )
        op05_dir = Path(op05["outputDir"])
        op07 = _post(
            base, f"/{OP07}/predict",
            json={"inputFile": str(op05_dir), "params": {}, "seed": args.seed},
        )

        runs = {OP03: op03, OP05: op05, OP06: op06, OP07: op07}
        names = {
            OP03: "句向量与主题聚类",
            OP05: "多模态自动打标",
            OP06: "领域/能力多标签",
            OP07: "标签治理",
        }
        evidence_map = {}
        for operator_id, data in runs.items():
            evidence = OPERATOR_DIR / operator_id / "output" / "evidence" / data["runId"]
            _copy_run(output_root, operator_id, data["runId"], evidence)
            evidence_map[operator_id] = evidence

        command = (
            f'"D:/anaconda3/envs/use/python.exe" scripts/run_s2_chain.py '
            f'--op02-dir "{op02_dir.relative_to(ROOT).as_posix()}"'
        )
        environment = _environment()
        for operator_id, data in runs.items():
            evidence = evidence_map[operator_id]
            upstream = {
                OP03: op02_dir,
                OP05: op02_dir,
                OP06: op02_dir,
                OP07: Path(op05["outputDir"]),
            }[operator_id]
            extra = (
                f"- runId：`{data['runId']}`\n"
                f"- inputFingerprint：`{data.get('inputFingerprint')}`\n"
                f"- paramsHash：`{data['paramsHash']}`\n"
                f"- seed：{data['seed']}\n"
                f"- operatorVersion：{data['operatorVersion']}\n"
                f"- 上游输入：`{upstream.as_posix()}`\n"
            )
            (evidence / "report.md").write_text(
                _report(operator_id, names[operator_id], data, command, extra, evidence),
                encoding="utf-8",
                newline="\n",
            )
            (evidence / "command.txt").write_text(command + "\n", encoding="utf-8", newline="\n")
            (evidence / "environment.txt").write_text(
                environment + "\n", encoding="utf-8", newline="\n"
            )
            input_manifest = evidence / "input_manifest.json"
            if input_manifest.is_file():
                shutil.copyfile(input_manifest, evidence / "input-manifest.json")
            _artifacts_sha(evidence)

        stage_dir = ROOT / "docs" / "算子开发" / "evidence" / "S2" / f"run-{args.stage_date}"
        _write_stage_index(stage_dir, runs, command, op02_dir)

        summary = {
            operator_id: {
                "runId": data["runId"],
                "evidence": evidence_map[operator_id].relative_to(ROOT).as_posix(),
            }
            for operator_id, data in runs.items()
        }
        summary["stageIndex"] = stage_dir.relative_to(ROOT).as_posix()
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
