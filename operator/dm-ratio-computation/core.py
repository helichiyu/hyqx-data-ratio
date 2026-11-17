"""OP-15 配比引擎（``ratio_weighted_plan_v1``）。

消费 OP-02 记录与 OP-05 标签：构建标签×来源库存，按可解释权重链路计算有效条数与
占比（最大余数法 0.01%），输出条数/权重/占比三列、投喂条数、校验单、未覆盖类别与缺口。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .utils import checks as checks_util
from .utils import inventory as inventory_util
from .utils import weights as weights_util
from .utils.common import (
    ensure_output_dir,
    ensure_under_roots,
    environment_roots,
    fingerprint_file,
    fingerprint_path,
    load_config,
    locate_records,
    now_iso,
    params_hash,
    resolve_relative,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-ratio-computation"
SEMANTIC_CODE = "ratio_weighted_plan_v1"
OPERATOR_VERSION = "0.1.2"
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
    if "target_total" in resolved:
        cfg["targets"]["targetTotal"] = int(resolved["target_total"])
    if "label_weights" in resolved and isinstance(resolved["label_weights"], dict):
        label_weights = {str(key): float(value) for key, value in resolved["label_weights"].items()}
    else:
        label_weights = {}
    output = ensure_output_dir(output_dir)
    _clean_output(output)

    records_path, records_root = locate_records(input_path)
    labels_path = _locate(resolved.get("labels_path"))
    labels = inventory_util.load_labels(labels_path, int(cfg["inventory"]["labelLevel"]))
    inventory = inventory_util.merge_records(labels, records_path)
    summary = inventory_util.summarize(inventory)

    rows = weights_util.compute_effective(inventory, label_weights, cfg)
    normalization = weights_util.normalize(rows, cfg)
    tree = checks_util.load_tree(resolve_relative("baseline/tree-snapshot.json"))
    validation = checks_util.evaluate(rows, normalization, tree, cfg)

    result_path = output / "result.jsonl"
    plan_path = output / "plan.json"
    validation_path = output / "validation.json"
    metrics_path = output / "metrics.json"
    input_manifest_path = output / "input_manifest.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, rows)
    write_json(plan_path, {"rows": rows, "normalization": normalization, "inventory": summary})
    write_json(validation_path, validation)

    fingerprint, records_bytes = fingerprint_file(records_path)
    input_fingerprint = fingerprint_path(input_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "inputFingerprint": f"sha256:{input_fingerprint}",
            "recordsBytes": records_bytes,
            "labelsPath": labels_path.as_posix() if labels_path else None,
            "inventory": summary,
            "note": "库存只读 OP-05 标签结果；无标签时仓库为空，校验单全部 failed。",
        },
    )

    failed_checks = [item["id"] for item in validation["checks"] if not item["passed"]]
    run_id = _run_id(input_fingerprint, resolved, resolved_seed)
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "inventory": summary,
        "labelCount": len(rows),
        "totalEffective": normalization["total"],
        "shareSum": round(sum(row["share"] for row in rows), 6),
        "normalizationError": normalization["error"],
        "normalizationUnit": normalization["unit"],
        "targetTotal": int(cfg["targets"]["targetTotal"]),
        "feedTotal": sum(row["feedCount"] for row in rows),
        "checks": validation["checks"],
        "checksPassed": len(validation["checks"]) - len(failed_checks),
        "checksTotal": len(validation["checks"]),
        "failedChecks": failed_checks,
        "uncoveredLevel1": validation["uncoveredLevel1"],
        "uncoveredLevel2": validation["uncoveredLevel2"],
        "totalGap": validation["totalGap"],
        "treeVersion": validation["treeVersion"],
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }
    write_json(metrics_path, metrics)

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    output_bytes = sum(item["bytes"] for item in artifacts)
    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": validation["treeVersion"],
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": len(rows),
        "successCount": len(rows),
        "failedCount": 0,
        "inputBytes": records_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / records_bytes, 6) if records_bytes else 0.0,
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "notes": [
            "有效条数 = 条数 × 标签权重 × 来源权重 × 偏见降权 × 角色/阶段系数（默认 1.0）。",
            "归一化用最大余数法，单位 10^-4；长尾最小 0.01%，不置零。",
            "校验单每项带实测值、阈值与来源；未通过项如实列出，不调整阈值凑通过。",
        ],
    }
    write_json(manifest_path, manifest)

    summary_json = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "runId": manifest["runId"],
        "inputFingerprint": manifest["inputFingerprint"],
        "paramsHash": manifest["paramsHash"],
        "seed": resolved_seed,
        "modelVersion": None,
        "treeVersion": validation["treeVersion"],
        "sampleCount": len(rows),
        "successCount": len(rows),
        "failedCount": 0,
        "metrics": metrics,
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(summary_path, summary_json)

    return {
        "modelVersion": None,
        "treeVersion": validation["treeVersion"],
        "sampleCount": len(rows),
        "successCount": len(rows),
        "failedCount": 0,
        "failedSamples": [],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "三列方案表见 result.jsonl；校验单见 validation.json。",
            "权重默认 1.0（Q-04 未提供），需业务确认后替换。",
        ],
    }


def _locate(raw: Any) -> Path | None:
    if not raw:
        return None
    try:
        target = ensure_under_roots(str(raw), environment_roots())
    except ValueError:
        return None
    if target.is_dir():
        candidate = target / "result.jsonl"
        if candidate.is_file():
            return candidate
        matches = sorted(target.glob("*.jsonl"))
        return matches[0] if matches else None
    return target if target.is_file() else None


def _clean_output(output: Path) -> None:
    for name in ("result.jsonl", "plan.json", "validation.json", "metrics.json", "manifest.json", "summary.json", "input_manifest.json"):
        (output / name).unlink(missing_ok=True)


def _collect_artifacts(output: Path, exclude: set[str]) -> list[dict[str, Any]]:
    items = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name in exclude:
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
