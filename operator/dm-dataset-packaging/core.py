"""OP-17 数据组装与打包（``prod_assembly_package_v1``）。

消费 OP-15 配方（每标签投喂配额）与 OP-02/OP-05 标准产物：
- 每条记录只归一个标签（最高置信度），按配额与固定 seed 确定性选样；
- 输出选样清单、层实抽/配额、偏差报告、Parquet 分片（zstd、modal/source/dt 分区）；
- manifest 逐文件记录条数/字节/MD5/SHA-256；checkpoint 支持中断续跑，不重复不丢样。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .utils import package as package_util
from .utils import select as select_util
from .utils import source as source_util
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

OPERATOR_ID = "dm-dataset-packaging"
SEMANTIC_CODE = "prod_assembly_package_v1"
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

    plan_rows, target_total, plan_path = source_util.load_plan(input_path)
    if not plan_rows:
        return _blocked(output, input_fingerprint, plan_path, "PLAN_ROWS_EMPTY", "OP-15 方案表为空", cfg, resolved_seed, resolved)
    if len(plan_rows) > int(cfg["limits"]["maxLabels"]):
        return _blocked(
            output, input_fingerprint, plan_path, "LABEL_LIMIT_EXCEEDED",
            f"标签数 {len(plan_rows)} 超过上限 {cfg['limits']['maxLabels']}", cfg, resolved_seed, resolved,
        )

    records_path, labels_path = _resolve_sources(plan_path, resolved)
    records, record_failures = source_util.load_records(records_path, int(cfg["limits"]["maxRecords"]))
    labels, label_failures = source_util.load_labels(labels_path, int(cfg["limits"]["maxRecords"]))
    if not records:
        return _blocked(output, input_fingerprint, plan_path, "RECORDS_EMPTY", "OP-02 记录为空", cfg, resolved_seed, resolved)
    if not labels:
        return _blocked(output, input_fingerprint, plan_path, "LABELS_EMPTY", "OP-05 标签为空", cfg, resolved_seed, resolved)

    index = source_util.build_index(plan_rows, records, labels)

    checkpoint_path = output / cfg["outputs"]["checkpointFile"]
    params_digest = params_hash(resolved)
    selected, quotas, checkpoint, resumed = select_util.select(
        plan_rows,
        index["assigned"],
        resolved_seed,
        params_digest,
        checkpoint_path,
        resume=bool(resolved.get("resume", True)),
    )
    if not selected:
        return _blocked(
            output, input_fingerprint, plan_path, "NOTHING_SELECTED",
            "没有可入选记录（标签不在配方、库存为空或配额为 0）", cfg, resolved_seed, resolved,
            detail={"skipped": len(index["skipped"]), "labels": len(plan_rows)},
        )

    enriched = []
    for item in selected:
        info = index["recordLabels"].get(item["record_id"]) or {}
        enriched.append(
            {
                **item,
                "confidence": info.get("confidence"),
                "level1": info.get("level1"),
                "level2": info.get("level2"),
            }
        )

    selected_path = output / cfg["outputs"]["selectedFile"]
    write_jsonl(selected_path, enriched)
    bias = select_util.bias_report(
        quotas,
        enriched,
        records,
        plan_rows,
        float(cfg["bias"]["maxDeviationWarn"]),
    )
    dataset = package_util.write_dataset(output, enriched, records, cfg)

    quota_path = output / cfg["outputs"]["quotaFile"]
    bias_path = output / cfg["outputs"]["biasFile"]
    failures_path = output / "failures.jsonl"
    write_json(quota_path, {"targetTotal": target_total, "labels": quotas})
    write_json(bias_path, bias)
    failures = []
    for item in record_failures:
        failures.append({**item, "stage": "records"})
    for item in label_failures:
        failures.append({**item, "stage": "labels"})
    for item in index["skipped"]:
        failures.append({**item, "stage": "selection"})
    write_jsonl(failures_path, failures)

    status_counts: dict[str, int] = {}
    for entry in quotas:
        status_counts[entry["status"]] = status_counts.get(entry["status"], 0) + 1
    total_quota = sum(entry["quota"] for entry in quotas)
    total_selected = len(enriched)
    selected_sources: dict[str, int] = {}
    selected_modals: dict[str, int] = {}
    for item in enriched:
        record = records.get(item["record_id"]) or {}
        source = str((record.get("partitions") or {}).get("source") or record.get("source") or "unknown")
        modal = str((record.get("partitions") or {}).get("modal") or record.get("modal") or "unknown")
        selected_sources[source] = selected_sources.get(source, 0) + 1
        selected_modals[modal] = selected_modals.get(modal, 0) + 1

    tree_version = index["treeVersions"][0] if index["treeVersions"] else None
    model_version = index["modelVersions"][0] if index["modelVersions"] else None

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": model_version,
        "runId": None,
        "paramsHash": f"sha256:{params_digest}",
        "seed": resolved_seed,
        "targetTotal": target_total,
        "totalQuota": total_quota,
        "selectedCount": total_selected,
        "selectionRate": round(total_selected / total_quota, 6) if total_quota > 0 else None,
        "labelCount": len(plan_rows),
        "labelStatus": status_counts,
        "inventoryGap": max(0, total_quota - total_selected),
        "selectedSources": dict(sorted(selected_sources.items())),
        "selectedModals": dict(sorted(selected_modals.items())),
        "duplicateRecords": total_selected - len({item["record_id"] for item in enriched}),
        "skippedCount": len(index["skipped"]),
        "failures": {
            "records": len(record_failures),
            "labels": len(label_failures),
            "selection": len(index["skipped"]),
        },
        "bias": {
            "maxDeviation": bias["maxDeviation"],
            "maxQuotaDeviation": bias["maxQuotaDeviation"],
            "maxSourceDeviation": bias["maxSourceDeviation"],
            "weightedMeanDeviation": bias["weightedMeanDeviation"],
            "warn": bias["warn"],
        },
        "dataset": {
            "fileCount": dataset["fileCount"],
            "rows": dataset["rows"],
            "bytes": dataset["bytes"],
            "partitionCount": len(dataset["partitionCounts"]),
            "compression": dataset["compression"],
        },
        "checkpoint": {"resumed": resumed, "completedLabels": len(checkpoint["completedLabels"])},
        "treeVersion": tree_version,
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }

    input_manifest = {
        "planPath": plan_path.as_posix(),
        "planFingerprint": f"sha256:{hashlib.sha256(plan_path.read_bytes()).hexdigest()}",
        "recordsPath": records_path.as_posix(),
        "recordsFingerprint": f"sha256:{hashlib.sha256(records_path.read_bytes()).hexdigest()}",
        "labelsPath": labels_path.as_posix(),
        "labelsFingerprint": f"sha256:{hashlib.sha256(labels_path.read_bytes()).hexdigest()}",
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "recordCount": len(records),
        "labelCount": len(labels),
        "targetTotal": target_total,
        "modelVersion": model_version,
        "treeVersion": tree_version,
        "note": "records/labels 由 OP-15 input_manifest 回退解析；生产环境应由平台传入不可变的内容寻址路径。",
    }
    run_id = _run_id(input_fingerprint, resolved, resolved_seed)
    metrics["runId"] = run_id
    write_json(output / "metrics.json", metrics)
    write_json(output / "input_manifest.json", input_manifest)

    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": model_version,
        "treeVersion": tree_version,
        "paramsHash": f"sha256:{params_digest}",
        "seed": resolved_seed,
        "sampleCount": total_selected,
        "successCount": total_selected,
        "failedCount": 0,
        "dataset": {
            "rows": dataset["rows"],
            "bytes": dataset["bytes"],
            "files": dataset["files"],
            "partitionCounts": dataset["partitionCounts"],
            "compression": dataset["compression"],
            "rowGroupRows": dataset["rowGroupRows"],
        },
        "quota": {"targetTotal": target_total, "totalQuota": total_quota, "status": status_counts},
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "notes": [
            "每条记录只归一个标签（最高置信度），成品无重复；标签内按 sha256(seed|record_id) 选样。",
            "Parquet 按 modal/source/dt 分区、zstd 压缩；manifest 逐文件记录 rows/bytes/MD5/SHA-256。",
            "库存不足时入选数小于配额，缺口如实写入 quota.json 与 metrics.inventoryGap。",
            "真值/合规资源未参与本算子；OP-18 负责评测。",
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
            "modelVersion": model_version,
            "treeVersion": tree_version,
            "sampleCount": total_selected,
            "successCount": total_selected,
            "failedCount": 0,
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )

    return {
        "modelVersion": model_version,
        "treeVersion": tree_version,
        "sampleCount": total_selected,
        "successCount": total_selected,
        "failedCount": 0,
        "failedSamples": failures[:100],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": selected_path.as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "result": {
            "targetTotal": target_total,
            "totalQuota": total_quota,
            "selectedCount": total_selected,
            "inventoryGap": metrics["inventoryGap"],
            "dataset": metrics["dataset"],
            "bias": bias,
            "manifestPath": (output / "manifest.json").as_posix(),
        },
        "notes": [
            "选样清单 selected.jsonl；层实抽/配额 quota.json；偏差 bias.json；成品 dataset/ 与 manifest.json。",
            "固定 seed 重跑与断点续跑均不重复、不丢样。",
        ],
    }


def _resolve_sources(plan_path: Path, params: dict[str, Any]) -> tuple[Path, Path]:
    manifest_path = plan_path.parent / "input_manifest.json"
    upstream: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            upstream = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            upstream = {}
    roots = environment_roots()
    records_raw = params.get("records_path") or upstream.get("recordsPath")
    labels_raw = params.get("labels_path") or upstream.get("labelsPath")
    if not records_raw:
        raise ValueError("缺少 records_path，且 OP-15 input_manifest 未记录 recordsPath")
    if not labels_raw:
        raise ValueError("缺少 labels_path，且 OP-15 input_manifest 未记录 labelsPath")
    records_root = ensure_under_roots(str(records_raw), roots)
    labels_root = ensure_under_roots(str(labels_raw), roots)
    records_path = source_util.locate_file(records_root, ("records.jsonl",))
    labels_path = source_util.locate_file(labels_root, ("result.jsonl",))
    return records_path, labels_path


def _blocked(
    output: Path,
    input_fingerprint: str,
    plan_path: Path,
    reason: str,
    message: str,
    cfg: dict[str, Any],
    seed: int,
    params: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    write_jsonl(output / "result.jsonl", [])
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
        "outputFilePath": (output / "result.jsonl").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "blockedReason": reason,
        "notes": [message, "未选样、未打包，不伪造成品。"],
    }


def _collect_artifacts(output: Path, exclude: set[str]) -> list[dict[str, Any]]:
    items = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name in exclude:
            continue
        if path.name.endswith(".tmp"):
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
