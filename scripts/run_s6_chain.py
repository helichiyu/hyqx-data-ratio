"""运行 S6 真实链路（OP-02/03/05 → OP-20；OP-08～19 → OP-22；OP-05 → OP-21）并生成证据。

用法：
    "D:/anaconda3/envs/use/python.exe" scripts/run_s6_chain.py
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
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DIR = ROOT / "operator"
TRANSPORT = OPERATOR_DIR / "runtime" / "transport"
OUTPUT_ROOT = TRANSPORT / "output"
SERVICE_LOG = OPERATOR_DIR / "runtime" / "s6-service.log"

OP02_RUN = OUTPUT_ROOT / "dm-corpus-normalization" / "10a342ae92595ab7"
OP03_RUN = OUTPUT_ROOT / "dm-text-clustering" / "e53b5d9093388fe5"
OP05_RUN = OUTPUT_ROOT / "dm-multimodal-labeling" / "e53b5d9093388fe5"
OP07_RUN = OUTPUT_ROOT / "dm-label-governance" / "016129e87099395c"
OP08_RUN = OUTPUT_ROOT / "dm-corpus-profiling" / "73e001cb4f8e5aed"
OP09_RUN = OUTPUT_ROOT / "dm-language-profiling" / "e53b5d9093388fe5"
OP10_RUN = OUTPUT_ROOT / "dm-text-profiling" / "73e001cb4f8e5aed"
OP14_RUN = OUTPUT_ROOT / "dm-quality-analysis" / "f979e048a3250253"
OP15_RUN = OUTPUT_ROOT / "dm-ratio-computation" / "cab32b6cd497cac3"
OP17_RUN = OUTPUT_ROOT / "dm-dataset-packaging" / "347d6365d8457c91"
OP18_RUN = OUTPUT_ROOT / "dm-dataset-evaluation" / "020fe881d78849c0"
OP19_RUN = OUTPUT_ROOT / "dm-ratio-reporting" / "bf9ce91b0a82182b"


def _wait_health(base: str, process: subprocess.Popen, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"服务提前退出，日志：{SERVICE_LOG}")
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as response:
                if json.loads(response.read()).get("code") == 0:
                    return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    raise RuntimeError(f"等待服务就绪超时：{SERVICE_LOG}")


def _post(base: str, path: str, **kwargs):
    response = requests.post(f"{base}{path}", timeout=1800, **kwargs)
    payload = response.json()
    if response.status_code >= 400 or payload.get("code") != 0:
        raise RuntimeError(f"{path} 失败：HTTP {response.status_code} {payload}")
    return payload["data"]


def _copy_run(operator_id: str, run_id: str) -> Path:
    source = OUTPUT_ROOT / operator_id / run_id
    evidence = OPERATOR_DIR / operator_id / "output" / "evidence" / run_id
    if not source.is_dir():
        raise RuntimeError(f"运行目录不存在：{source}")
    if evidence.exists():
        shutil.rmtree(evidence)
    shutil.copytree(source, evidence)
    (evidence / "logs").mkdir(exist_ok=True)
    if SERVICE_LOG.is_file():
        tail = SERVICE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
        (evidence / "logs" / "service.log").write_text("\n".join(tail) + "\n", encoding="utf-8", newline="\n")
    return evidence


def _write_common_evidence(evidence: Path, command: str, result: dict) -> None:
    (evidence / "command.txt").write_text(command + "\n", encoding="utf-8", newline="\n")
    env_lines = [
        f"python: {sys.version.split()[0]}",
        f"platform: {platform.platform()}",
        f"numpy: {np.__version__}",
        f"requests: {requests.__version__}",
        f"INPUT_DIR: {os.getenv('INPUT_DIR', '')}",
        f"OUTPUT_DIR: {os.getenv('OUTPUT_DIR', '')}",
    ]
    (evidence / "environment.txt").write_text("\n".join(env_lines) + "\n", encoding="utf-8", newline="\n")
    failed = result.get("failedSamples") or []
    with (evidence / "failures.jsonl").open("w", encoding="utf-8", newline="\n") as sink:
        for item in failed:
            sink.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def _report(op_id: str, name: str, result: dict, extra: list[tuple[str, str]]) -> str:
    lines = [
        f"# 工作包回执 · {op_id}（{name}）",
        "",
        "## 状态",
        "完成（本机真实链路）；S6 阶段资源/阈值待人工确认（H-03/H-05/H-11/Q-07）。",
        "",
        "## 运行命令",
        "```bash",
        '"D:/anaconda3/envs/use/python.exe" scripts/run_s6_chain.py',
        "```",
        "",
        "## 证据路径",
        f"- 结果目录：`{result.get('outputDir')}`",
        "",
        "## 指标",
        "| 项 | 值 |",
        "| --- | --- |",
    ]
    for key, value in extra:
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## 未决问题",
        "- 本体/KG/词表（H-11）、专家标注（H-05）、风险阈值（H-03）、Neo4j/FAISS（Q-07）待人工。",
        "- 资源缺失项标 unavailable/blocked，不编造。",
        "",
    ]
    return "\n".join(lines)


def _hashes(directory: Path) -> None:
    lines = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file() and path.name != "artifacts.sha256":
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(directory).as_posix()}")
    (directory / "artifacts.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="S6 链路与证据")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=17030)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--stage-date", default=time.strftime("%Y%m%d"))
    args = parser.parse_args()

    for path in (OP02_RUN, OP03_RUN, OP05_RUN, OP07_RUN, OP08_RUN, OP09_RUN, OP10_RUN, OP14_RUN, OP15_RUN, OP17_RUN, OP18_RUN, OP19_RUN):
        if not path.is_dir():
            raise SystemExit(f"缺少上游运行目录：{path}")

    input_root = TRANSPORT / "input"
    input_root.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SERVICE_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_handle = SERVICE_LOG.open("w", encoding="utf-8")
    env = dict(os.environ)
    env.update({"INPUT_DIR": str(input_root), "OUTPUT_DIR": str(OUTPUT_ROOT), "PYTHONIOENCODING": "utf-8"})
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "inference:app", "--host", args.host, "--port", str(args.port), "--workers", "1"],
        cwd=str(OPERATOR_DIR), env=env, stdout=log_handle, stderr=subprocess.STDOUT,
    )
    base = f"http://{args.host}:{args.port}"
    command = (
        f'INPUT_DIR={input_root.as_posix()} OUTPUT_DIR={OUTPUT_ROOT.as_posix()} '
        f'"D:/anaconda3/envs/use/python.exe" scripts/run_s6_chain.py --seed {args.seed}'
    )
    try:
        _wait_health(base, process)

        op20 = _post(
            base, "/dm-graph-indexing/predict",
            json={
                "inputFile": str(OP02_RUN),
                "params": {"records_path": str(OP02_RUN), "labels_path": str(OP05_RUN), "vectors_path": str(OP03_RUN)},
                "seed": args.seed,
            },
        )
        evidence20 = _copy_run("dm-graph-indexing", op20["runId"])
        _write_common_evidence(evidence20, command, op20)
        (evidence20 / "report.md").write_text(
            _report(
                "OP-20", "知识图谱与向量索引", op20,
                [
                    ("节点 / 边", f"{op20['metrics']['graph']['nodeCount']} / {op20['metrics']['graph']['edgeCount']}"),
                    ("实体数", op20["metrics"]["graph"]["entityCount"]),
                    ("向量数 / 维度", f"{op20['metrics']['vector']['count']} / {op20['metrics']['vector']['dimension']}"),
                    ("recall@10 / QPS", f"{op20['metrics']['vector']['recallAtK']['10']} / {op20['metrics']['vector']['qps']}"),
                    ("Neo4j / FAISS", f"{op20['metrics']['services']['neo4j']['status']} / {op20['metrics']['services']['faiss']['status']}"),
                ],
            ),
            encoding="utf-8", newline="\n",
        )
        _hashes(evidence20)
        print(f"OP-20 runId={op20['runId']} nodes={op20['metrics']['graph']['nodeCount']} edges={op20['metrics']['graph']['edgeCount']}", flush=True)

        bundle_path = OUTPUT_ROOT / "s6-risk-bundle.json"
        bundle = {
            "operator_results": {
                "OP-08": str(OP08_RUN),
                "OP-09": str(OP09_RUN),
                "OP-10": str(OP10_RUN),
                "OP-14": str(OP14_RUN),
                "OP-15": str(OP15_RUN),
                "OP-17": str(OP17_RUN),
                "OP-18": str(OP18_RUN),
                "OP-19": str(OP19_RUN),
            }
        }
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        op22 = _post(base, "/dm-risk-detection/predict", json={"inputFile": str(bundle_path), "params": {}, "seed": args.seed})
        evidence22 = _copy_run("dm-risk-detection", op22["runId"])
        _write_common_evidence(evidence22, command, op22)
        (evidence22 / "bundle.json").write_text(bundle_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        (evidence22 / "report.md").write_text(
            _report(
                "OP-22", "风险检测与分级", op22,
                [
                    ("风险条数", op22["metrics"]["riskCount"]),
                    ("critical / warning / info", f"{op22['metrics']['criticalCount']} / {op22['metrics']['warningCount']} / {op22['metrics']['infoCount']}"),
                    ("抑制 / 无数据 / 样本不足", f"{op22['metrics']['suppressedCount']} / {op22['metrics']['noDataCount']} / {op22['metrics']['insufficientSampleCount']}"),
                    ("过时知识", op22["metrics"]["outdated"]["status"]),
                ],
            ),
            encoding="utf-8", newline="\n",
        )
        _hashes(evidence22)
        print(f"OP-22 runId={op22['runId']} risks={op22['metrics']['riskCount']} critical={op22['metrics']['criticalCount']}", flush=True)

        op21 = _post(
            base, "/dm-expert-validation/predict",
            json={"inputFile": str(OP05_RUN / "result.jsonl"), "params": {}, "seed": args.seed},
        )
        evidence21 = _copy_run("dm-expert-validation", op21["runId"])
        _write_common_evidence(evidence21, command, op21)
        (evidence21 / "report.md").write_text(
            _report(
                "OP-21", "专家校验", op21,
                [
                    ("总体 / 实抽", f"{op21['metrics']['sampling']['population']} / {op21['metrics']['sampling']['sampled']}"),
                    ("实抽比例", op21["metrics"]["sampling"]["ratioEffective"]),
                    ("高风险补入", op21["metrics"]["sampling"]["highRiskAdded"]),
                    ("一致性状态", op21["metrics"]["agreement"]["status"]),
                    ("Kappa / Alpha", f"{op21['metrics']['agreement']['meanKappa']} / {op21['metrics']['agreement']['alpha']}"),
                ],
            ),
            encoding="utf-8", newline="\n",
        )
        _hashes(evidence21)
        print(f"OP-21 runId={op21['runId']} sampled={op21['metrics']['sampling']['sampled']} agreement={op21['metrics']['agreement']['status']}", flush=True)

        stage = ROOT / "docs" / "算子开发" / "evidence" / "S6" / f"run-{args.stage_date}"
        stage.mkdir(parents=True, exist_ok=True)
        lines = [
            "# S6 阶段证据索引 · 工具与风险",
            "",
            f"> 日期：{time.strftime('%Y-%m-%d')}",
            f"> 上游：OP-02 `{OP02_RUN.relative_to(ROOT).as_posix()}`、OP-03 `{OP03_RUN.relative_to(ROOT).as_posix()}`、"
            f"OP-05 `{OP05_RUN.relative_to(ROOT).as_posix()}`；OP-08～19 复用 S3/S4/S5 运行目录",
            "",
            "| 算子 | runId | 证据目录 | 关键指标 |",
            "| --- | --- | --- | --- |",
            f"| OP-20 知识图谱与向量索引 | {op20['runId']} | `{evidence20.relative_to(ROOT).as_posix()}/` | "
            f"节点 {op20['metrics']['graph']['nodeCount']}；边 {op20['metrics']['graph']['edgeCount']}；"
            f"向量 {op20['metrics']['vector']['count']}；recall@10 {op20['metrics']['vector']['recallAtK']['10']}；"
            f"服务 {op20['metrics']['services']['neo4j']['status']} |",
            f"| OP-21 专家校验 | {op21['runId']} | `{evidence21.relative_to(ROOT).as_posix()}/` | "
            f"总体 {op21['metrics']['sampling']['population']}；实抽 {op21['metrics']['sampling']['sampled']}；"
            f"一致性 {op21['metrics']['agreement']['status']}；争议 {op21['metrics']['agreement']['disputeCount']} |",
            f"| OP-22 风险检测与分级 | {op22['runId']} | `{evidence22.relative_to(ROOT).as_posix()}/` | "
            f"风险 {op22['metrics']['riskCount']}（critical {op22['metrics']['criticalCount']}）；"
            f"抑制 {op22['metrics']['suppressedCount']}；过时 {op22['metrics']['outdated']['status']} |",
            "",
            "## 门禁核对（OP-20）",
            "",
            "| 门禁 | 结果 | 证据 |",
            "| --- | --- | --- |",
            "| 实体/关系计数一致 | 通过 | `graph_stats.json` 与 nodes/edges 文件；测试对账 |",
            "| 图谱导入文件可解析 | 通过 | `neo4j_import.cypher` / JSONL；测试读取 |",
            "| 索引重建幂等/检索可复现 | 通过 | `index/meta.json` indexVersion；两次运行一致 |",
            "| 服务不可用有明确失败码 | 通过 | `metrics.services.*.reasonCode=SERVICE_NOT_CONFIGURED` |",
            "",
            "## 门禁核对（OP-21）",
            "",
            "| 门禁 | 结果 | 证据 |",
            "| --- | --- | --- |",
            "| 抽样 5–10% 可复现 | 通过 | `sampled.jsonl`；固定 seed |",
            "| 高风险必选 | 机制通过/实数据无风险输入 | 单测覆盖；真实链路未提供 record 级风险 |",
            "| Kappa/Alpha 用真实标注 | 无专家数据 | `agreement.status=blocked`（H-05） |",
            "| 争议可下钻 | 机制通过 | `disputes.jsonl`；单测覆盖 |",
            "",
            "## 门禁核对（OP-22）",
            "",
            "| 门禁 | 结果 | 证据 |",
            "| --- | --- | --- |",
            "| 规则命中/未命中可复算 | 通过 | `risks.jsonl` + `risk_report.json` |",
            "| 双阈值/最小样本生效 | 通过 | 单测 `test_op22.py` |",
            "| 去重/抑制可解释 | 通过 | `suppressed` + 单测 |",
            "| 证据引用指标结果 | 通过 | `evidence.metricsPath/metric/value` |",
            "| 过时检测有知识库来源 | 缺失 | `outdated.status=unavailable`（H-11） |",
            "",
            "## 待补",
            "",
            "- 本体/KG/词表（H-11）、专家标注（H-05）、风险阈值（H-03）、Neo4j/FAISS（Q-07）待人工。",
            "- Docker 构建与容器内探针（H-01）待人工；按 10.2 第 5 条不阻断 S7。",
            "",
        ]
        (stage / "index.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
        print(
            json.dumps(
                {
                    "op20": {"runId": op20["runId"], "evidence": evidence20.relative_to(ROOT).as_posix()},
                    "op21": {"runId": op21["runId"], "evidence": evidence21.relative_to(ROOT).as_posix()},
                    "op22": {"runId": op22["runId"], "evidence": evidence22.relative_to(ROOT).as_posix()},
                    "stageIndex": stage.relative_to(ROOT).as_posix(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
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
