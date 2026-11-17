"""OP-21 专家校验（``tool_expert_validation_v1``）。

对 To-verify 对象做 5%–10% 分层抽样（固定 seed、高风险必选），
消费专家标注计算 Cohen's Kappa / Krippendorff's Alpha、共识、逐标签 P/R/F1 与争议 TopN。
无专家标注时抽样仍产出，一致性指标标 ``blocked``，不编造。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .utils import agreement as agreement_util
from .utils import sample as sample_util
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

OPERATOR_ID = "dm-expert-validation"
SEMANTIC_CODE = "tool_expert_validation_v1"
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
    input_file = Path(input_path).resolve()
    objects, failures = sample_util.load_objects(input_file, int(cfg["sampling"]["maxRecords"]))
    if not objects:
        return _blocked(output, input_fingerprint, "OBJECTS_EMPTY", "待校验对象为空", cfg, resolved_seed, resolved)

    risk_path = _optional_path(resolved.get("risk_path"))
    risks = sample_util.load_risk(risk_path)
    sampled, sample_stats = sample_util.sample(objects, risks, cfg, resolved_seed)
    expert_path = _optional_path(resolved.get("expert_path"))
    ratings, expert_failures = agreement_util.load_expert(expert_path, int(cfg["agreement"]["minRaters"]))
    agreement = agreement_util.evaluate(sampled, ratings, cfg)
    for failure in expert_failures:
        failures.append({**failure, "stage": "expert"})

    write_jsonl(
        output / "sampled.jsonl",
        [
            {
                "record_id": item["record_id"],
                "label": item["label"],
                "level1": item.get("level1"),
                "riskLevel": item.get("riskLevel"),
                "stratum": item.get("stratum"),
                "selectedBy": item.get("selectedBy"),
            }
            for item in sampled
        ],
    )
    write_json(output / "agreement.json", agreement)
    write_jsonl(output / "disputes.jsonl", agreement.get("disputes") or [])
    write_jsonl(output / "failures.jsonl", failures)

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    run_id = _run_id(input_fingerprint, resolved, resolved_seed)
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "treeVersion": None,
        "sampling": sample_stats,
        "agreement": {
            "status": agreement["status"],
            "blockedReason": agreement.get("blockedReason"),
            "kappa": agreement.get("kappa"),
            "alpha": agreement.get("alpha"),
            "meanKappa": (agreement.get("kappa") or {}).get("meanKappa"),
            "accuracyVsConsensus": agreement.get("accuracyVsConsensus"),
            "macroF1VsConsensus": agreement.get("macroF1VsConsensus"),
            "disputeCount": agreement.get("disputeCount"),
            "sampledWithAnnotations": agreement.get("sampledWithAnnotations"),
        },
        "riskPath": risk_path.as_posix() if risk_path else None,
        "expertPath": expert_path.as_posix() if expert_path else None,
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }
    write_json(output / "metrics.json", metrics)
    write_json(
        output / "input_manifest.json",
        {
            "inputFingerprint": f"sha256:{input_fingerprint}",
            "objectsFile": input_file.as_posix(),
            "objectCount": len(objects),
            "riskPath": risk_path.as_posix() if risk_path else None,
            "expertPath": expert_path.as_posix() if expert_path else None,
            "expertRecords": len(ratings),
            "note": "专家标注未提供时一致性指标 blocked；抽样仍产出。",
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
        "sampleCount": len(sampled),
        "successCount": len(sampled),
        "failedCount": len(failures),
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "notes": [
            "5%–10% 分层抽样、固定 seed、高风险必选；实抽比例与分层统计写入 metrics.sampling。",
            "Kappa/Alpha 只用真实专家标注；无标注时 blocked，不编造。",
            "专家任务派发/签署/工单归平台，不在算子内。",
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
            "sampleCount": len(sampled),
            "successCount": len(sampled),
            "failedCount": len(failures),
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )

    return {
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": len(sampled),
        "successCount": len(sampled),
        "failedCount": len(failures),
        "failedSamples": failures[:100],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": (output / "sampled.jsonl").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "result": {
            "sampling": sample_stats,
            "agreement": agreement,
            "disputes": agreement.get("disputes") or [],
        },
        "notes": [
            "抽样清单 sampled.jsonl；一致性 agreement.json；争议 disputes.jsonl。",
            "无专家标注时一致性 blocked，抽样仍可用。",
        ],
    }


def _optional_path(raw: Any) -> Path | None:
    if not raw:
        return None
    try:
        return ensure_under_roots(str(raw), environment_roots())
    except ValueError:
        return None


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
        "notes": [message, "未抽样/未计算一致性，不编造。"],
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
