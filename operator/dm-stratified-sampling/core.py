"""OP-04 分层抽样（``corpus_shard_stratified_sample_v1``）。

按 来源 × 主题簇（OP-03）× 质量等级（OP-14）分层，Neyman 分配配额并做确定性抽样；
输出层配额、样本清单、实抽比例、代表性与未达标层。缺失维度标记 MISSING，不猜测。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .utils import neyman, sampler, strata
from .utils.common import (
    ensure_output_dir,
    ensure_under_roots,
    environment_roots,
    fingerprint_file,
    load_config,
    locate_records,
    now_iso,
    params_hash,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-stratified-sampling"
SEMANTIC_CODE = "corpus_shard_stratified_sample_v1"
OPERATOR_VERSION = "0.1.0"
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
    _clean_output(output)

    records_path, records_root = locate_records(input_path)
    clusters = strata.load_mapping(_locate(resolved.get("cluster_path")), "cluster")
    qualities = strata.load_mapping(_locate(resolved.get("quality_path")), "difficultyLevel")

    strata_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"records": [], "values": []})
    record_order: list[str] = []
    failures: list[dict[str, Any]] = []
    max_records = int(resolved.get("max_records", cfg["limits"]["maxRecords"]))
    attempted = 0

    with records_path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if number > max_records:
                break
            stripped = line.strip()
            if not stripped:
                continue
            attempted += 1
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append({"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": exc.msg})
                continue
            record_id = str(record.get("record_id") or f"line:{number}")
            key = strata.stratum_key(record, clusters, qualities, cfg)
            size = _unit_size(record)
            strata_map[key]["records"].append(record_id)
            strata_map[key]["values"].append(size)
            record_order.append(record_id)

    population = len(record_order)
    share_rule = cfg["sampling"]["share"]
    if population >= int(share_rule["large"]["thresholdRecords"]):
        share = float(share_rule["large"]["min"])
        share_band = "large"
    else:
        share = float(share_rule["small"]["default"])
        share_band = "small"
    share = float(resolved.get("share", share))
    target = max(1, int(round(population * share))) if population else 0
    caps = {key: len(value["records"]) for key, value in strata_map.items()}
    allocation = neyman.allocate(
        dict(strata_map), target, int(cfg["sampling"]["minPerStratum"]), caps
    )

    selected: list[dict[str, Any]] = []
    per_stratum: list[dict[str, Any]] = []
    for key in sorted(strata_map):
        quota = allocation["quotas"][key]
        picked = sampler.sample_stratum(strata_map[key]["records"], quota, resolved_seed)
        for item in picked:
            selected.append({"record_id": item["record_id"], "stratum": key, "hash": item["hash"]})
        population_count = len(strata_map[key]["records"])
        per_stratum.append(
            {
                "stratum": key,
                "population": population_count,
                "quota": quota,
                "sampled": len(picked),
                "populationShare": round(population_count / population, 6) if population else 0.0,
                "cv": allocation["cvs"][key],
                "ideal": allocation["ideal"][key],
                "unmet": quota > population_count,
            }
        )
    sampled_total = len(selected)
    for row in per_stratum:
        row["sampleShare"] = round(row["sampled"] / sampled_total, 6) if sampled_total else 0.0
        row["bias"] = round(row["sampleShare"] - row["populationShare"], 6)

    sampled_ids = {item["record_id"] for item in selected}
    duplicate_free = len(sampled_ids) == len(selected)
    total_min = int(cfg["sampling"]["minTotal"])
    metrics = {
        "population": population,
        "target": target,
        "allocated": allocation["allocated"],
        "sampled": len(selected),
        "shareUsed": share,
        "shareBand": share_band,
        "shareRules": share_rule,
        "targetMet": len(selected) == target,
        "allocationBasis": allocation["basis"],
        "unmetQuota": allocation["unmet"],
        "minTotal": total_min,
        "minTotalMet": population >= total_min,
        "stratumCount": len(strata_map),
        "duplicateFree": duplicate_free,
        "actualRatio": round(len(selected) / population, 6) if population else 0.0,
        "maxAbsBias": round(max((abs(row["bias"]) for row in per_stratum), default=0.0), 6),
        "unmetStrata": [row["stratum"] for row in per_stratum if row["unmet"]],
        "skippedDimensions": {
            "cluster": "provided" if clusters else "MISSING",
            "quality": "provided" if qualities else "MISSING",
        },
        "failedCount": len(failures),
        "seed": resolved_seed,
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }

    result_path = output / "result.jsonl"
    quota_path = output / "quota_table.json"
    failures_path = output / "failures.jsonl"
    metrics_path = output / "metrics.json"
    input_manifest_path = output / "input_manifest.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, selected)
    write_json(quota_path, {"target": target, "strata": per_stratum})
    write_jsonl(failures_path, failures)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "clusterMapping": len(clusters),
            "qualityMapping": len(qualities),
            "note": "抽样单位大小：文本字数；媒体用 metadata.sizeBytes；无值按 0。",
        },
    )
    write_json(metrics_path, metrics)

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    output_bytes = sum(item["bytes"] for item in artifacts)
    manifest = {
        "runId": _run_id(fingerprint, resolved, resolved_seed),
        "inputFingerprint": f"sha256:{fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": attempted,
        "successCount": len(selected),
        "failedCount": len(failures),
        "inputBytes": records_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / records_bytes, 6) if records_bytes else 0.0,
        "artifacts": artifacts,
        "failedSamples": failures,
        "createdAt": now_iso(),
        "notes": [
            "Neyman 配额 n_h = n·(N_h·CV_h)/Σ(N_h·CV_h)；CV 全为 0 时按 N_h 比例分配。",
            "抽样按 sha256(seed|record_id) 升序取前 n_h，无放回、可复现。",
            "缺失主题簇/质量等级时对应维度标 MISSING，不猜测。",
        ],
    }
    write_json(manifest_path, manifest)

    summary = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "runId": manifest["runId"],
        "inputFingerprint": manifest["inputFingerprint"],
        "paramsHash": manifest["paramsHash"],
        "seed": resolved_seed,
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": attempted,
        "successCount": len(selected),
        "failedCount": len(failures),
        "metrics": metrics,
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(summary_path, summary)

    return {
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": attempted,
        "successCount": len(selected),
        "failedCount": len(failures),
        "failedSamples": failures,
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "配额、实抽、偏差与未达标层均在 quota_table.json 中逐层可复算。",
            "最小样本 10 万条约束在样例批次不满足，metrics.minTotalMet=false 如实记录。",
        ],
    }


def _unit_size(record: dict[str, Any]) -> float:
    text = record.get("text")
    if isinstance(text, str) and text:
        return float(len(text))
    size = (record.get("metadata") or {}).get("sizeBytes")
    return float(size) if isinstance(size, (int, float)) else 0.0


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
    for name in ("result.jsonl", "quota_table.json", "failures.jsonl", "metrics.json", "manifest.json", "summary.json", "input_manifest.json"):
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
