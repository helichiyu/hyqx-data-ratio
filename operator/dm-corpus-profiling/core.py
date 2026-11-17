"""OP-08 规模、来源与领域画像（``corpus_profile_scale_source_domain_v1``）。

消费 OP-02 ``records.jsonl``：流式聚合条数/字符/时长/帧/存储与分位数，计算六类
来源占比与 AHP 可信度；提供 OP-06 领域标签时计算领域覆盖与缺口。全部指标来自
真实记录或配置基线，无常量/随机数伪造。
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .utils import ahp, domain, source
from .utils.common import (
    RECORD_REQUIRED,
    ensure_output_dir,
    ensure_under_roots,
    environment_roots,
    fingerprint_file,
    load_config,
    locate_records,
    now_iso,
    params_hash,
    percentile_nearest_rank,
    resolve_relative,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-corpus-profiling"
SEMANTIC_CODE = "corpus_profile_scale_source_domain_v1"
OPERATOR_VERSION = "0.1.0"
DEFAULT_SEED = 42
STANDARD_SUFFIX = {"image": ("images", ".webp"), "audio": ("audio", ".wav"), "video": ("video", ".mp4")}


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
    domain_labels = _locate_domain_labels(resolved)
    tree_path = resolve_relative(cfg["domain"]["treeRelativePath"])
    tree = domain.load_tree(tree_path)

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    dts_by_source: dict[str, list[str | None]] = defaultdict(list)
    completeness_by_source: dict[str, list[float]] = defaultdict(list)
    chars: list[float] = []
    durations: list[float] = []
    frames: list[float] = []
    sizes: list[float] = []
    text_chars = 0
    text_bytes = 0
    duration_total = 0.0
    frame_total = 0
    size_total = 0
    standard_total = 0
    standard_missing = 0
    captured: list[str] = []
    attempted = 0

    max_records = int(resolved.get("max_records", cfg["limits"]["maxRecords"]))
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
                failures.append(
                    {"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": exc.msg}
                )
                continue
            missing = [key for key in RECORD_REQUIRED if key not in record]
            if missing:
                failures.append(
                    {
                        "id": record.get("record_id") or f"line:{number}",
                        "reasonCode": "RECORD_FIELD_MISSING",
                        "detail": ",".join(missing),
                    }
                )
                continue

            record_id = str(record["record_id"])
            modal = str(record["modal"])
            source_alias = str(record["source"])
            metadata = record["metadata"] or {}
            quality = record["quality"] or {}
            partitions = record["partitions"] or {}
            dt = partitions.get("dt")
            text = record.get("text")
            text_value = text if isinstance(text, str) else ""
            char_count = len(text_value)
            byte_count = len(text_value.encode("utf-8"))
            duration = metadata.get("durationSec")
            frame_count = metadata.get("frameCount")
            size_bytes = metadata.get("sizeBytes")
            standard_bytes = _standard_bytes(records_root, record_id, modal)
            if modal in STANDARD_SUFFIX:
                if standard_bytes is None:
                    standard_missing += 1
                else:
                    standard_total += standard_bytes

            counts[modal] += 1
            source_counts[source_alias] += 1
            dts_by_source[source_alias].append(str(dt) if dt else None)
            completeness = quality.get("completeness")
            completeness_by_source[source_alias].append(
                float(completeness) if isinstance(completeness, (int, float)) else 0.0
            )
            text_chars += char_count
            text_bytes += byte_count
            if isinstance(duration, (int, float)):
                duration_total += float(duration)
                durations.append(float(duration))
            if isinstance(frame_count, (int, float)):
                frame_total += int(frame_count)
                frames.append(float(frame_count))
            if isinstance(size_bytes, (int, float)):
                size_total += int(size_bytes)
                sizes.append(float(size_bytes))
            if char_count:
                chars.append(float(char_count))
            if metadata.get("capturedAt"):
                captured.append(str(metadata["capturedAt"]))

            rows.append(
                {
                    "record_id": record_id,
                    "modal": modal,
                    "source": source_alias,
                    "textChars": char_count,
                    "textBytes": byte_count,
                    "durationSec": duration,
                    "frameCount": frame_count,
                    "sizeBytes": size_bytes,
                    "standardBytes": standard_bytes,
                    "dt": dt,
                    "completeness": completeness,
                }
            )

    percentiles = list(resolved.get("percentiles") or cfg["percentiles"])
    as_of = _resolve_as_of(resolved, [str(item["dt"]) for item in rows if item.get("dt")])
    source_report = source.class_scores(
        dict(source_counts), dts_by_source, completeness_by_source, cfg, as_of
    )
    domain_report = domain.domain_coverage(domain_labels, tree, counts.get("text", 0))

    scale = {
        "recordCount": len(rows),
        "modalCounts": dict(sorted(counts.items())),
        "textChars": text_chars,
        "textBytes": text_bytes,
        "durationSec": round(duration_total, 3),
        "frameCount": frame_total,
        "sizeBytes": size_total,
        "standardBytes": standard_total,
        "standardCompressionRatio": (
            round(standard_total / size_total, 6) if size_total and standard_total else None
        ),
        "standardMissing": standard_missing,
        "percentiles": {
            "textChars": {
                f"p{int(p)}": percentile_nearest_rank(chars, float(p)) for p in percentiles
            },
            "durationSec": {
                f"p{int(p)}": percentile_nearest_rank(durations, float(p)) for p in percentiles
            },
            "frameCount": {
                f"p{int(p)}": percentile_nearest_rank(frames, float(p)) for p in percentiles
            },
            "sizeBytes": {
                f"p{int(p)}": percentile_nearest_rank(sizes, float(p)) for p in percentiles
            },
            "method": "nearest-rank：排序后取 ceil(p/100·N) 位",
        },
        "capturedAtPresent": len(captured),
    }

    result_path = output / "result.jsonl"
    failures_path = output / "failures.jsonl"
    metrics_path = output / "metrics.json"
    source_path = output / "source_distribution.json"
    domain_path = output / "domain_coverage.json"
    input_manifest_path = output / "input_manifest.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, rows)
    write_jsonl(failures_path, failures)
    write_json(source_path, source_report)
    write_json(domain_path, domain_report)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "domainLabelsPath": domain_labels.as_posix() if domain_labels else None,
            "treePath": tree_path.as_posix(),
            "note": "领域覆盖只读 OP-06 结果文件，不 import 其它算子代码。",
        },
    )

    failures_by_reason = dict(sorted(Counter(item["reasonCode"] for item in failures).items()))
    metrics = {
        "scale": scale,
        "sourceDistribution": {
            "shareSumPercent": source_report["shareSumPercent"],
            "corpusCredibility": source_report["corpusCredibility"],
            "ahp": source_report["ahp"],
            "classes": {
                name: {
                    "count": item["count"],
                    "sharePercent": item["sharePercent"],
                    "credibility": item["credibility"],
                    "dimensionScores": item["dimensionScores"],
                }
                for name, item in source_report["classes"].items()
            },
        },
        "domainCoverage": domain_report,
        "failedCount": len(failures),
        "failuresByReason": failures_by_reason,
        "treeVersion": tree["treeVersion"],
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
        "modelVersion": None,
        "treeVersion": tree["treeVersion"],
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
            "规模/分位数/来源占比来自真实记录；AHP 权重由判断矩阵计算，CR<0.1 才视为一致。",
            "领域覆盖需要 OP-06 结果；缺失时 status=unavailable，不编造分布。",
            "无人工标注，效果类指标不产出。",
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
        "treeVersion": tree["treeVersion"],
        "sampleCount": attempted,
        "successCount": len(rows),
        "failedCount": len(failures),
        "metrics": metrics,
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(summary_path, summary)

    return {
        "modelVersion": None,
        "treeVersion": tree["treeVersion"],
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
            "分位数口径为 nearest-rank，见 metrics.scale.percentiles.method。",
            "来源 AHP 分值：authority/transparency 为联调初值，freshness/evaluation 由数据实时计算。",
        ],
    }


def _standard_bytes(records_root: Path, record_id: str, modal: str) -> int | None:
    parts = STANDARD_SUFFIX.get(modal)
    if not parts:
        return None
    folder, suffix = parts
    path = records_root / "standard" / folder / f"{record_id}{suffix}"
    return path.stat().st_size if path.is_file() else None


def _locate_domain_labels(params: dict[str, Any]) -> Path | None:
    raw = params.get("domain_labels_path")
    if not raw:
        return None
    try:
        target = ensure_under_roots(str(raw), environment_roots())
    except ValueError:
        return None
    if target.is_dir():
        for name in ("result.jsonl", "domain.jsonl"):
            candidate = target / name
            if candidate.is_file():
                return candidate
        matches = sorted(target.glob("*.jsonl"))
        return matches[0] if matches else None
    return target if target.is_file() else None


def _resolve_as_of(params: dict[str, Any], dts: list[str]) -> date:
    raw = params.get("as_of")
    if raw:
        return date.fromisoformat(str(raw)[:10])
    parsed = sorted(dt[:10] for dt in dts if dt)
    if parsed:
        return date.fromisoformat(parsed[-1])
    return date.today()


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
                "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
            }
        )
    return items


def _run_id(fingerprint: str, params: dict[str, Any], seed: int) -> str:
    import hashlib

    return hashlib.sha256(
        f"{fingerprint}|{OPERATOR_VERSION}|{params_hash(params)}|{seed}".encode("utf-8")
    ).hexdigest()[:16]
