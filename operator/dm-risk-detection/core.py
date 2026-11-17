"""OP-22 风险检测与分级（``risk_metric_rule_v1``）。

消费 OP-08～OP-19 的 ``metrics.json``，按 JSON 规则 DSL 做双阈值/最小样本判定，
输出去重/抑制后的风险条目（类型/等级/指标/证据/建议）；不重复计算指标。
过时知识检测在知识库缺失时标 ``unavailable``，不编造过时率。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .utils import rules as rules_util
from .utils.common import (
    ensure_output_dir,
    ensure_under_roots,
    environment_roots,
    fingerprint_path,
    load_config,
    now_iso,
    params_hash,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-risk-detection"
SEMANTIC_CODE = "risk_metric_rule_v1"
OPERATOR_VERSION = "0.1.0"
DEFAULT_SEED = 42

OPERATOR_CODES = {
    "dm-corpus-profiling": "OP-08",
    "dm-language-profiling": "OP-09",
    "dm-text-profiling": "OP-10",
    "dm-speech-analysis": "OP-11",
    "dm-visual-analysis": "OP-12",
    "dm-knowledge-analysis": "OP-13",
    "dm-quality-analysis": "OP-14",
    "dm-ratio-computation": "OP-15",
    "dm-ratio-analysis": "OP-16",
    "dm-dataset-packaging": "OP-17",
    "dm-dataset-evaluation": "OP-18",
    "dm-ratio-reporting": "OP-19",
}


def run(
    input_path: str,
    params: dict | None = None,
    seed: int | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    started = time.time()
    cfg = load_config()
    resolved = dict(params or {})
    resolved_seed = DEFAULT_SEED if seed is None else int(seed)
    output = ensure_output_dir(output_dir)
    input_fingerprint = fingerprint_path(input_path)

    raw_results = _resolve_results(input_path, resolved)
    if not raw_results:
        return _blocked(
            output, input_fingerprint, "OPERATOR_RESULTS_REQUIRED",
            "未提供各算子结果目录（params.operator_results 或 bundle.json）", cfg, resolved_seed, resolved,
        )
    if len(raw_results) > int(cfg["limits"]["maxOperatorResults"]):
        return _blocked(
            output, input_fingerprint, "OPERATOR_RESULTS_TOO_MANY",
            f"算子结果数超过上限 {cfg['limits']['maxOperatorResults']}", cfg, resolved_seed, resolved,
        )

    results: dict[str, str] = {}
    for raw_key, raw_path in raw_results.items():
        key = OPERATOR_CODES.get(str(raw_key), str(raw_key))
        try:
            results[key] = ensure_under_roots(str(raw_path), environment_roots()).as_posix()
        except ValueError:
            results[key] = str(raw_path)
    metrics, problems = _load_metrics(results)
    if not metrics:
        return _blocked(
            output, input_fingerprint, "OPERATOR_METRICS_EMPTY",
            "所有算子结果均缺少可读 metrics.json", cfg, resolved_seed, resolved,
            detail={"problems": problems},
        )

    evidence_paths = {
        operator: (
            (Path(raw) / "metrics.json").as_posix() if Path(raw).is_dir() else str(raw)
        )
        for operator, raw in results.items()
    }
    report = rules_util.evaluate(metrics, problems, cfg, evidence_paths)
    write_jsonl(output / "risks.jsonl", report["risks"])
    write_json(output / "risk_report.json", report)

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    run_id = _run_id(input_fingerprint, resolved, resolved_seed)
    metrics_out = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "treeVersion": None,
        "operatorsConsumed": len(metrics),
        "rules": len(cfg["rules"]),
        "evaluatedRules": report["evaluatedRules"],
        "rawHits": report["rawHits"],
        "riskCount": len(report["risks"]),
        "criticalCount": sum(1 for item in report["risks"] if item["level"] == "critical"),
        "warningCount": sum(1 for item in report["risks"] if item["level"] == "warning"),
        "infoCount": sum(1 for item in report["risks"] if item["level"] == "info"),
        "suppressedCount": report["suppressedCount"],
        "noDataCount": len(report["noData"]),
        "insufficientSampleCount": len(report["insufficientSample"]),
        "outdated": report["outdated"],
        "missingOperators": problems,
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }
    write_json(output / "metrics.json", metrics_out)
    write_json(
        output / "input_manifest.json",
        {
            "inputFingerprint": f"sha256:{input_fingerprint}",
            "operatorResults": results,
            "loadedOperators": sorted(metrics),
            "problems": problems,
            "note": "风险规则只读取上游 metrics.json，不重复计算指标；证据路径逐条写入 risk_report。",
        },
    )
    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": len(report["risks"]),
        "successCount": len(report["risks"]),
        "failedCount": len(report["noData"]),
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "notes": [
            "风险条目只引用上游 metrics 的指标路径与值，不重复计算指标。",
            "双阈值 critical/warn 定级；minSample 不足时规则不执行并单列。",
            "去重按 operator+type 保留最高等级；抑制按类型上限保留高等级条目。",
            "过时知识检测需知识库（H-11），未提供时 unavailable。",
        ],
    }
    write_json(output / "manifest.json", manifest)
    write_json(
        output / "summary.json",
        {
            "operatorId": OPERATOR_ID,
            "semanticCode": SEMANTIC_CODE,
            "operatorVersion": OPERATOR_VERSION,
            "runId": run_id,
            "inputFingerprint": manifest["inputFingerprint"],
            "paramsHash": manifest["paramsHash"],
            "seed": resolved_seed,
            "modelVersion": None,
            "treeVersion": None,
            "sampleCount": len(report["risks"]),
            "successCount": len(report["risks"]),
            "failedCount": len(report["noData"]),
            "metrics": metrics_out,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )

    return {
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": len(report["risks"]),
        "successCount": len(report["risks"]),
        "failedCount": len(report["noData"]),
        "failedSamples": report["noData"],
        "metrics": metrics_out,
        "artifacts": artifacts,
        "outputFilePath": (output / "risks.jsonl").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "result": report,
        "notes": [
            "风险条目 risks.jsonl；完整报告 risk_report.json（含去重/抑制/无数据/样本不足/过时状态）。",
            "不重复计算指标；每条风险引用上游 metrics 路径与值。",
        ],
    }


def _resolve_results(input_path: str, params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("operator_results")
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    path = Path(input_path).resolve()
    payload: Any = None
    if path.is_file() and path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif path.is_dir() and (path / "bundle.json").is_file():
        payload = json.loads((path / "bundle.json").read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        nested = payload.get("operator_results") or payload.get("operatorResults")
        if isinstance(nested, dict):
            return {str(key): value for key, value in nested.items()}
    return {}


def _load_metrics(results: dict[str, str]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    metrics: dict[str, dict[str, Any]] = {}
    problems: dict[str, str] = {}
    for operator, raw_path in results.items():
        path = Path(raw_path)
        candidate = path / "metrics.json" if path.is_dir() else path
        if not candidate.is_file():
            problems[operator] = f"metrics.json 不存在：{candidate}"
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems[operator] = f"metrics.json 不可解析：{exc}"
            continue
        if isinstance(payload, dict):
            metrics[operator] = payload
        else:
            problems[operator] = "metrics.json 不是对象"
    return metrics, problems


def _blocked(
    output: Path,
    input_fingerprint: str,
    reason: str,
    message: str,
    cfg: dict[str, Any],
    seed: int,
    params: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _run_id(input_fingerprint, params, seed)
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(params)}",
        "seed": seed,
        "treeVersion": None,
        "blockedReason": reason,
        "message": message,
        "detail": detail or {},
        "provisional": True,
        "deterministic": True,
        "generatedAt": now_iso(),
    }
    write_json(output / "metrics.json", metrics)
    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(params)}",
        "seed": seed,
        "sampleCount": 0,
        "successCount": 0,
        "failedCount": 0,
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "blockedReason": reason,
    }
    write_json(output / "manifest.json", manifest)
    write_json(
        output / "summary.json",
        {
            "operatorId": OPERATOR_ID,
            "semanticCode": SEMANTIC_CODE,
            "operatorVersion": OPERATOR_VERSION,
            "runId": run_id,
            "inputFingerprint": manifest["inputFingerprint"],
            "paramsHash": manifest["paramsHash"],
            "seed": seed,
            "modelVersion": None,
            "treeVersion": None,
            "sampleCount": 0,
            "successCount": 0,
            "failedCount": 0,
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )
    return {
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": 0,
        "successCount": 0,
        "failedCount": 0,
        "failedSamples": [],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": (output / "risks.jsonl").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "blockedReason": reason,
        "notes": [message, "未生成风险条目，不编造。"],
    }


def _collect_artifacts(output: Path, exclude: set[str]) -> list[dict[str, Any]]:
    items = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name in exclude or path.name.endswith(".tmp"):
            continue
        items.append(
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return items


def _run_id(fingerprint: str, params: dict[str, Any], seed: int) -> str:
    return hashlib.sha256(
        f"{fingerprint}|{OPERATOR_VERSION}|{params_hash(params)}|{seed}".encode("utf-8")
    ).hexdigest()[:16]
