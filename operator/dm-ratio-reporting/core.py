"""OP-19 配比分析与报告（``prod_ratio_report_v1``）。

消费 OP-08～OP-18 的真实 ``metrics.json``，聚合九维结果、综合评分、状态矩阵与结论摘要，
输出可被平台渲染的报告数据包；HTML 渲染可选，渲染失败不影响数据包完整性。
缺数据的维度标 ``no_data`` 并列入 missing，不编造。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .utils import collect as collect_util
from .utils import score as score_util
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

OPERATOR_ID = "dm-ratio-reporting"
SEMANTIC_CODE = "prod_ratio_report_v1"
OPERATOR_VERSION = "0.1.1"
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
    "dm-label-governance": "OP-07",
    "dm-multimodal-labeling": "OP-05",
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
            f"算子结果数 {len(raw_results)} 超过上限 {cfg['limits']['maxOperatorResults']}", cfg, resolved_seed, resolved,
        )

    results: dict[str, str] = {}
    for raw_key, raw_path in raw_results.items():
        key = OPERATOR_CODES.get(str(raw_key), str(raw_key))
        try:
            results[key] = ensure_under_roots(str(raw_path), environment_roots()).as_posix()
        except ValueError:
            results[key] = str(raw_path)
    metrics_by_operator, problems = collect_util.load_metrics(results)
    if not metrics_by_operator:
        return _blocked(
            output, input_fingerprint, "OPERATOR_METRICS_EMPTY",
            "所有算子结果均缺少可读 metrics.json", cfg, resolved_seed, resolved,
            detail={"problems": problems},
        )

    dimensions = collect_util.collect(metrics_by_operator, cfg, problems)
    overall = score_util.overall(dimensions, cfg)
    conclusions = score_util.conclusions(dimensions, overall)
    operator_versions = {
        operator: payload.get("operatorVersion") for operator, payload in sorted(metrics_by_operator.items())
    }
    tree_versions = sorted(
        {str(payload.get("treeVersion")) for payload in metrics_by_operator.values() if payload.get("treeVersion")}
    )

    report = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "runId": None,
        "seed": resolved_seed,
        "generatedAt": now_iso(),
        "treeVersion": tree_versions[0] if len(tree_versions) == 1 else (tree_versions or None),
        "operatorVersions": operator_versions,
        "dimensions": dimensions,
        "overall": overall,
        "statusMatrix": [
            {
                "key": item["key"],
                "nameZh": item["nameZh"],
                "operator": item["operator"],
                "score": item["score"],
                "grade": item["grade"],
                "weight": item["weight"],
                "status": item["status"],
                "reason": item.get("reason"),
            }
            for item in dimensions
        ],
        "conclusions": conclusions,
        "missingOperators": problems,
        "evidence": results,
        "provisional": True,
        "deterministic": True,
    }

    render = {"status": "skipped", "path": None, "error": None}
    if bool(cfg["render"].get("html")) or resolved.get("render_html"):
        try:
            html = score_util.render_html(report, str(cfg["render"]["title"]))
            html_path = output / "report.html"
            html_path.write_text(html, encoding="utf-8", newline="\n")
            render = {"status": "ok", "path": html_path.as_posix(), "error": None}
        except Exception as exc:  # noqa: BLE001 - 渲染失败不影响数据包
            render = {"status": "failed", "path": None, "error": f"{type(exc).__name__}: {exc}"}
    report["render"] = render

    run_id = _run_id(input_fingerprint, resolved, resolved_seed)
    report["runId"] = run_id
    write_json(output / "report_package.json", report)
    write_json(output / "status_matrix.json", {"rows": report["statusMatrix"], "overall": overall})
    write_jsonl(output / "conclusions.jsonl", conclusions)
    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})

    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "treeVersion": report["treeVersion"],
        "operatorsConsumed": len(metrics_by_operator),
        "dimensionsTotal": len(dimensions),
        "dimensionsAvailable": overall["dimensionsAvailable"],
        "overallScore": overall["score"],
        "overallGrade": overall["grade"],
        "missing": overall["missing"],
        "missingOperators": problems,
        "operatorVersions": operator_versions,
        "render": render,
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }
    write_json(output / "metrics.json", metrics)

    input_manifest = {
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorResults": results,
        "operatorFingerprints": {
            key: f"sha256:{fingerprint_path(path)}" if Path(path).exists() else None
            for key, path in results.items()
        },
        "loadedOperators": sorted(metrics_by_operator),
        "problems": problems,
        "note": "每个维度必须来自真实算子 metrics.json；缺失维度标 no_data，不编造。",
    }
    write_json(output / "input_manifest.json", input_manifest)

    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": report["treeVersion"],
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": len(dimensions),
        "successCount": overall["dimensionsAvailable"],
        "failedCount": len(overall["missing"]),
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "notes": [
            "九维结果全部来自真实算子 metrics.json；缺数据维度标 no_data 并列入 missing。",
            "综合分只聚合可用维度并重归一权重；阈值与权重为联调初值（H-03）。",
            "报告数据包 report_package.json 可被平台渲染；HTML 渲染失败不影响数据包。",
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
            "treeVersion": report["treeVersion"],
            "sampleCount": len(dimensions),
            "successCount": overall["dimensionsAvailable"],
            "failedCount": len(overall["missing"]),
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )

    return {
        "modelVersion": None,
        "treeVersion": report["treeVersion"],
        "sampleCount": len(dimensions),
        "successCount": overall["dimensionsAvailable"],
        "failedCount": len(overall["missing"]),
        "failedSamples": overall["missing"],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": (output / "report_package.json").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "result": {
            "overall": overall,
            "dimensions": report["statusMatrix"],
            "conclusions": conclusions,
            "render": render,
            "reportPackagePath": (output / "report_package.json").as_posix(),
        },
        "notes": [
            "九维状态矩阵见 status_matrix.json；完整数据包 report_package.json；结论见 conclusions.jsonl。",
            "缺失维度如实列入 missing，不按 0 计、不编造。",
        ],
    }


def _resolve_results(input_path: str, params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("operator_results")
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    path = Path(input_path).resolve()
    if path.is_file() and path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif path.is_dir() and (path / "bundle.json").is_file():
        payload = json.loads((path / "bundle.json").read_text(encoding="utf-8"))
    else:
        return {}
    if isinstance(payload, dict):
        nested = payload.get("operator_results") or payload.get("operatorResults")
        if isinstance(nested, dict):
            return {str(key): value for key, value in nested.items()}
    return {}


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
        "outputFilePath": (output / "report_package.json").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "blockedReason": reason,
        "notes": [message, "未生成九维报告，不编造评分。"],
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
