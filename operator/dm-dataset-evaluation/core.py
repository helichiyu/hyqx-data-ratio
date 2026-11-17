"""OP-18 数据评测（``prod_evaluation_v1``）。

消费 OP-17 成品 manifest/Parquet，按 5%–10% 固定 seed 分层抽样：
- 有真值：精确/前缀准确率、逐模态准确率、宏 F1、混淆矩阵、错标清单；
- 无真值（H-05 未提供）：准确率类指标标 `null` + `blockedReason`，只出代理指标，不冒充准确率；
- 合规/版权：词表/哈希库缺失时 `unavailable`，不编造；
- 综合质量分只聚合可用分项，权重来自配置并记录来源。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .utils import compliance as compliance_util
from .utils import dataset as dataset_util
from .utils import metrics as metrics_util
from .utils import sample as sample_util
from .utils.common import (
    ensure_output_dir,
    ensure_under_roots,
    environment_roots,
    fingerprint_path,
    load_config,
    now_iso,
    params_hash,
    resolve_relative,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-dataset-evaluation"
SEMANTIC_CODE = "prod_evaluation_v1"
OPERATOR_VERSION = "0.1.1"
DEFAULT_SEED = 42


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
    run_dir = Path(input_path).resolve()
    if not run_dir.is_dir():
        return _blocked(output, input_fingerprint, "INPUT_NOT_DIRECTORY", "OP-18 输入必须是 OP-17 运行目录", cfg, resolved_seed, resolved)

    manifest = dataset_util.load_manifest(run_dir)
    records = dataset_util.load_records(run_dir, manifest)
    if not records:
        return _blocked(output, input_fingerprint, "DATASET_EMPTY", "OP-17 成品没有记录", cfg, resolved_seed, resolved)

    ratio = float(resolved.get("ratio") or cfg["sampling"]["ratio"])
    ratio = min(1.0, max(0.01, ratio))
    sampled, sample_stats = sample_util.stratified_sample(
        records, ratio, resolved_seed, int(cfg["sampling"]["minPerModal"])
    )
    legal_paths = metrics_util.load_tree_paths(resolve_relative("baseline/tree-snapshot.json"))
    proxy = metrics_util.proxy_metrics(
        sampled,
        records,
        legal_paths,
        float(cfg["matching"]["lowConfidenceThreshold"]),
    )

    truth_path = _optional_path(resolved.get("truth_path"))
    truth_failures: list[dict[str, Any]] = []
    if truth_path is not None:
        truth, truth_failures = metrics_util.load_truth(truth_path, int(cfg["limits"]["maxTruthRecords"]))
        truth_report = metrics_util.evaluate_truth(sampled, records, truth, cfg)
        truth_report["truthPath"] = truth_path.as_posix()
        truth_report["truthRecords"] = len(truth)
    else:
        truth_report = {
            "status": "unavailable",
            "blockedReason": "TRUTH_REQUIRED",
            "message": "未提供人工真值（H-05），准确率/F1/混淆矩阵标 null。",
            "accuracy": None,
            "prefixAccuracy": None,
            "macroF1": None,
            "confusion": None,
            "wrongLabels": [],
            "evaluated": 0,
        }

    terms_path = _optional_path(resolved.get("compliance_terms_path"))
    hashes_path = _optional_path(resolved.get("copyright_hashes_path"))
    terms = compliance_util.load_terms(terms_path)
    hashes = compliance_util.load_hashes(hashes_path)
    compliance = compliance_util.evaluate(
        sampled,
        records,
        terms,
        hashes,
        int(cfg["compliance"]["maxHits"]),
    )
    compliance["termsPath"] = terms_path.as_posix() if terms_path else None
    compliance["hashesPath"] = hashes_path.as_posix() if hashes_path else None

    score = _composite_score(truth_report, proxy, compliance, cfg)

    model_version = manifest.get("modelVersion")
    tree_version = manifest.get("treeVersion")
    version_check = _check_version_consistency(resolved.get("labels_path"), model_version, tree_version)
    if version_check.get("status") == "mismatch":
        return _blocked(
            output,
            input_fingerprint,
            "MODEL_TREE_MISMATCH",
            "评测标签模型/树版本与 OP-17 透传的 OP-05 版本不一致，拒绝混用两套口径",
            cfg,
            resolved_seed,
            resolved,
        )

    sampled_path = output / "sampled.jsonl"
    write_jsonl(
        sampled_path,
        [
            {
                "record_id": item["record_id"],
                "modal": item["modal"],
                "sampleRank": item["sampleRank"],
                "label": (records.get(item["record_id"]) or {}).get("label"),
                "confidence": (records.get(item["record_id"]) or {}).get("confidence"),
            }
            for item in sampled
        ],
    )
    evaluation = {
        "sampling": sample_stats,
        "truth": truth_report,
        "proxy": proxy,
        "compliance": compliance,
        "score": score,
        "versionCheck": version_check,
    }
    write_json(output / "evaluation.json", evaluation)
    if truth_report.get("confusion") is not None:
        write_json(
            output / "confusion.json",
            {"labels": truth_report.get("confusionLabels") or [], "matrix": truth_report["confusion"]},
        )
    write_jsonl(output / "wrong_labels.jsonl", truth_report.get("wrongLabels") or [])
    write_json(output / "compliance.json", compliance)
    failures = list(truth_failures)
    write_jsonl(output / "failures.jsonl", failures)

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    run_id = _run_id(input_fingerprint, resolved, resolved_seed)
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": model_version,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "treeVersion": tree_version,
        "sampleSize": len(sampled),
        "population": len(records),
        "sampling": sample_stats,
        "truth": {
            "status": truth_report.get("status"),
            "blockedReason": truth_report.get("blockedReason"),
            "accuracy": truth_report.get("accuracy"),
            "prefixAccuracy": truth_report.get("prefixAccuracy"),
            "macroF1": truth_report.get("macroF1"),
            "evaluated": truth_report.get("evaluated"),
            "missingTruth": truth_report.get("missingTruth"),
        },
        "proxy": proxy,
        "compliance": {
            "status": compliance.get("status"),
            "reasonCode": compliance.get("reasonCode"),
            "hitCount": compliance.get("hitCount"),
            "hitRate": compliance.get("hitRate"),
            "passRate": compliance.get("passRate"),
        },
        "score": score,
        "versionCheck": version_check,
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }
    write_json(output / "metrics.json", metrics)
    write_json(
        output / "input_manifest.json",
        {
            "datasetRunDir": run_dir.as_posix(),
            "datasetManifest": (run_dir / "manifest.json").as_posix(),
            "datasetRunId": manifest.get("runId"),
            "inputFingerprint": f"sha256:{input_fingerprint}",
            "recordCount": len(records),
            "modelVersion": model_version,
            "treeVersion": tree_version,
            "truthPath": truth_path.as_posix() if truth_path else None,
            "note": "评测与 OP-05 共用 OP-17 透传的 modelVersion/treeVersion；真值缺失时效果指标为 null。",
        },
    )

    manifest_out = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": model_version,
        "treeVersion": tree_version,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": len(sampled),
        "successCount": len(sampled),
        "failedCount": len(failures),
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "notes": [
            "抽样按模态分层、sha256(seed|record_id) 排序，比例 5%–10%。",
            "无真值时准确率/F1/混淆矩阵为 null，代理指标明确 proxy=true。",
            "合规/版权资源缺失时 unavailable，不编造命中。",
            "综合分只聚合可用分项并重归一权重。",
        ],
    }
    write_json(output / "manifest.json", manifest_out)
    write_json(
        output / "summary.json",
        {
            "operatorId": OPERATOR_ID,
            "semanticCode": SEMANTIC_CODE,
            "operatorVersion": OPERATOR_VERSION,
            "runId": run_id,
            "inputFingerprint": manifest_out["inputFingerprint"],
            "paramsHash": manifest_out["paramsHash"],
            "seed": resolved_seed,
            "modelVersion": model_version,
            "treeVersion": tree_version,
            "sampleCount": len(sampled),
            "successCount": len(sampled),
            "failedCount": len(failures),
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )

    return {
        "modelVersion": model_version,
        "treeVersion": tree_version,
        "sampleCount": len(sampled),
        "successCount": len(sampled),
        "failedCount": len(failures),
        "failedSamples": failures[:100],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": sampled_path.as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "result": {
            "sampleSize": len(sampled),
            "sampling": sample_stats,
            "truth": metrics["truth"],
            "proxy": proxy,
            "compliance": metrics["compliance"],
            "score": score,
        },
        "notes": [
            "抽样清单 sampled.jsonl；评测 evaluation.json；混淆 confusion.json；错标 wrong_labels.jsonl；合规 compliance.json。",
            "真值/合规资源缺失时如实标 null/unavailable，不编造。",
        ],
    }


def _optional_path(raw: Any) -> Path | None:
    if not raw:
        return None
    try:
        return ensure_under_roots(str(raw), environment_roots())
    except ValueError:
        return None


def _composite_score(
    truth_report: dict[str, Any], proxy: dict[str, Any], compliance: dict[str, Any], cfg: dict[str, Any]
) -> dict[str, Any]:
    weights = cfg["score"]["weights"]
    components = {
        "labelAccuracy": truth_report.get("accuracy") if truth_report.get("status") == "ok" else None,
        "pathLegality": proxy.get("pathLegalityRate"),
        "completeness": proxy.get("meanCompleteness"),
        "compliance": compliance.get("passRate") if compliance.get("status") == "ok" else None,
    }
    available = {key: float(value) for key, value in components.items() if isinstance(value, (int, float))}
    weight_sum = sum(float(weights.get(key, 0.0)) for key in available)
    if weight_sum <= 0:
        score = None
    else:
        score = sum(float(weights.get(key, 0.0)) * value for key, value in available.items()) / weight_sum
    thresholds = cfg["score"]["thresholds"]
    if score is None:
        grade = "no_data"
    elif score >= float(thresholds["excellent"]):
        grade = "excellent"
    elif score >= float(thresholds["good"]):
        grade = "good"
    elif score >= float(thresholds["pass"]):
        grade = "pass"
    else:
        grade = "fail"
    scope = "full" if "labelAccuracy" in available else "proxy_only"
    if scope == "proxy_only" and grade not in {"no_data", "fail"}:
        # 无真值时综合分只由代理指标构成，等级加 proxy_ 前缀，避免被误读为效果评测。
        grade = f"proxy_{grade}"
    return {
        "score": round(score, 10) if score is not None else None,
        "grade": grade,
        "scope": scope,
        "note": (
            "无人工真值，综合分仅由路径合法率/完整率等代理指标构成，不等价于模型准确率（H-05）。"
            if scope == "proxy_only"
            else "综合分包含标签准确率与可用代理指标。"
        ),
        "components": {
            key: {
                "value": round(components[key], 10) if isinstance(components[key], (int, float)) else None,
                "weight": float(weights.get(key, 0.0)),
                "available": key in available,
            }
            for key in components
        },
        "weightSumUsed": round(weight_sum, 10),
        "thresholds": thresholds,
        "definition": "综合分 = Σ 可用分项×权重 / Σ 可用权重；不可用分项剔除，不按 0 计。",
    }


def _check_version_consistency(raw_labels: Any, model_version: Any, tree_version: Any) -> dict[str, Any]:
    if not raw_labels:
        return {"status": "skipped", "reason": "未提供 labels_path"}
    try:
        path = ensure_under_roots(str(raw_labels), environment_roots())
    except ValueError:
        return {"status": "invalid", "reason": "labels_path 不在允许根目录内"}
    manifest_path = path / "manifest.json" if path.is_dir() else path.parent / "manifest.json"
    if not manifest_path.is_file():
        return {"status": "unknown", "reason": "labels_path 缺少 manifest.json"}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unknown", "reason": "labels manifest 不可解析"}
    label_model = payload.get("modelVersion")
    label_tree = payload.get("treeVersion")
    consistent = label_model == model_version and label_tree == tree_version
    return {
        "status": "ok" if consistent else "mismatch",
        "datasetModelVersion": model_version,
        "datasetTreeVersion": tree_version,
        "labelsModelVersion": label_model,
        "labelsTreeVersion": label_tree,
    }


def _blocked(
    output: Path,
    input_fingerprint: str,
    reason: str,
    message: str,
    cfg: dict[str, Any],
    seed: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    write_jsonl(output / "sampled.jsonl", [])
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
        "outputFilePath": (output / "sampled.jsonl").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "blockedReason": reason,
        "notes": [message, "未抽样、未评测，不编造指标。"],
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
