"""OP-09 语言、地域与时效画像（``corpus_profile_language_region_time_v1``）。

消费 OP-02 记录：语种识别（文字体系 + 功能词规则）、地域字段统计、时间抽取与
新鲜度。置信度低于阈值标 mixed/unknown；无时间标 unknown；无地域字段标 unavailable。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from .utils import lang, region, timeparse
from .utils.common import (
    ensure_output_dir,
    fingerprint_file,
    load_config,
    locate_records,
    now_iso,
    params_hash,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-language-profiling"
SEMANTIC_CODE = "corpus_profile_language_region_time_v1"
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
    max_records = int(resolved.get("max_records", cfg["limits"]["maxRecords"]))
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    language_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    year_counts: Counter[str] = Counter()
    quarter_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    confidence_values: list[float] = []
    region_inputs: list[dict[str, Any]] = []
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
            if not isinstance(record, dict):
                failures.append({"id": f"line:{number}", "reasonCode": "RECORD_NOT_OBJECT"})
                continue

            record_id = str(record.get("record_id") or f"line:{number}")
            text = record.get("text") if isinstance(record.get("text"), str) else None
            metadata = record.get("metadata") or {}
            partitions = record.get("partitions") or {}
            region_inputs.append(record)

            detected = lang.detect(text, cfg)
            time_info = timeparse.extract(metadata.get("capturedAt"), text, partitions.get("dt"), cfg)

            language_counts[detected["language"]] += 1
            status_counts[detected["status"]] += 1
            confidence_values.append(float(detected["confidence"]))
            source_counts[time_info["timeSource"]] += 1

            rows.append(
                {
                    "record_id": record_id,
                    "modal": record.get("modal"),
                    "language": detected["language"],
                    "confidence": detected["confidence"],
                    "status": detected["status"],
                    "reasonCode": detected.get("reasonCode"),
                    "timeSource": time_info["timeSource"],
                    "year": time_info["year"],
                    "quarter": time_info["quarter"],
                    "freshness": None,
                    "hasRegion": any(metadata.get(field) for field in cfg["region"]["fields"]),
                }
            )

    as_of = _resolve_as_of(resolved, [row["year"] for row in rows if row["year"]])
    freshness_values: list[float] = []
    for row in rows:
        value = timeparse.freshness(row["year"], as_of, cfg)
        row["freshness"] = round(value, 6) if row["year"] else None
        if row["year"] is None:
            year_counts["unknown"] += 1
            continue
        year_counts[str(row["year"])] += 1
        freshness_values.append(value)
        if row["quarter"]:
            quarter_counts[f"{row['year']}-Q{row['quarter']}"] += 1

    region_report = region.collect(region_inputs, cfg)
    stale_threshold = float(cfg["time"]["staleThreshold"])
    corpus_freshness = round(sum(freshness_values) / len(freshness_values), 6) if freshness_values else None
    stale = sum(1 for value in freshness_values if value < stale_threshold)

    result_path = output / "result.jsonl"
    failures_path = output / "failures.jsonl"
    metrics_path = output / "metrics.json"
    region_path = output / "region_distribution.json"
    input_manifest_path = output / "input_manifest.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, rows)
    write_jsonl(failures_path, failures)
    write_json(region_path, region_report)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "asOf": as_of.isoformat(),
            "note": "语种/时间/地域全部来自记录本身；无模型、无外部地理库。",
        },
    )

    metrics = {
        "language": {
            "counts": dict(sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))),
            "shares": _shares(language_counts, attempted),
            "statusCounts": dict(sorted(status_counts.items())),
            "confidenceMean": round(sum(confidence_values) / len(confidence_values), 6) if confidence_values else None,
            "minConfidence": cfg["language"]["minConfidence"],
            "method": "unicode-script + function-words (rule-based)",
        },
        "time": {
            "yearCounts": dict(sorted(year_counts.items())),
            "quarterCounts": dict(sorted(quarter_counts.items())),
            "timeSourceCounts": dict(sorted(source_counts.items())),
            "freshnessMean": corpus_freshness,
            "freshnessWeights": cfg["time"]["freshnessWeights"],
            "staleThreshold": stale_threshold,
            "staleCount": stale,
            "staleShare": round(stale / len(freshness_values), 6) if freshness_values else None,
            "knownTimeRatio": round(len(freshness_values) / attempted, 6) if attempted else 0.0,
            "asOf": as_of.isoformat(),
        },
        "region": region_report,
        "failedCount": len(failures),
        "failuresByReason": dict(sorted(Counter(item["reasonCode"] for item in failures).items())),
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }
    write_json(metrics_path, metrics)

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    output_bytes = sum(item["bytes"] for item in artifacts)
    manifest = {
        "runId": _run_id(fingerprint, resolved, resolved_seed),
        "inputFingerprint": f"sha256:{fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": "unicode-script-heuristics-v1",
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": attempted,
        "successCount": len(rows),
        "failedCount": len(failures),
        "inputBytes": records_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / records_bytes, 6) if records_bytes else 0.0,
        "artifacts": artifacts,
        "failedSamples": failures,
        "createdAt": now_iso(),
        "notes": [
            "无 fastText/CLD3 权重，语种识别为文字体系 + 功能词规则，置信度=主导语言文字占比。",
            "地域只认记录 metadata 的 region/country/timezone；缺失时 unavailable。",
            "时间优先级 capturedAt > 正文年份 > partitions.dt（ingest_dt）；无时间标 unknown。",
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
        "modelVersion": manifest["modelVersion"],
        "treeVersion": None,
        "sampleCount": attempted,
        "successCount": len(rows),
        "failedCount": len(failures),
        "metrics": metrics,
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(summary_path, summary)

    return {
        "modelVersion": manifest["modelVersion"],
        "treeVersion": None,
        "sampleCount": attempted,
        "successCount": len(rows),
        "failedCount": len(failures),
        "failedSamples": failures,
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "语种置信度<0.85 或第二文字占比>=0.15 时标 mixed/unknown，不强行归类。",
            "新鲜度 = 近1年×0.6+近3年×0.3+3年以上×0.1；<0.4 计为过时风险。",
        ],
    }


def _resolve_as_of(params: dict[str, Any], years: list[int]) -> date:
    raw = params.get("as_of")
    if raw:
        return date.fromisoformat(str(raw)[:10])
    if years:
        return date(max(years), 12, 31)
    return date.today()


def _shares(counts: Counter[str], total: int) -> dict[str, float]:
    if not total:
        return {}
    return {
        name: round(count / total, 6)
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    }


def _clean_output(output: Path) -> None:
    for name in ("result.jsonl", "failures.jsonl", "metrics.json", "manifest.json", "summary.json", "input_manifest.json"):
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
