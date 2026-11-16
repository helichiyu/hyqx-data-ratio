"""OP-02 标准化、元数据与去重（``corpus_ingest_normalize_index_v1``）。

消费 OP-01 的 ``result.jsonl``（只读文件契约，不 import OP-01 代码）：
标准化文本/图像/音频/视频 → 按 modal/source/dt 分区写 Parquet → 元数据宽表/索引
→ 去重/异常清单 → 跨模态关联 → manifest/metrics。所有产物可复算、重跑覆盖同目录。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import wave
from collections import Counter
from pathlib import Path
from typing import Any

from .utils import dedup, index, readers, schema, writer
from .utils.common import (
    ensure_output_dir,
    file_hashes,
    fingerprint_file,
    load_config,
    params_hash,
    relative_posix,
    write_json,
    write_jsonl,
)
from .utils.hashes import simhash64

OPERATOR_ID = "dm-corpus-normalization"
SEMANTIC_CODE = "corpus_ingest_normalize_index_v1"
OPERATOR_VERSION = "0.1.0"
DEFAULT_SEED = 42


def run(
    input_path: str,
    params: dict | None = None,
    seed: int | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    cfg = load_config("normalize.json")
    resolved_params = dict(params or {})
    resolved_seed = DEFAULT_SEED if seed is None else int(seed)
    _apply_param_overrides(cfg, resolved_params)
    output = ensure_output_dir(output_dir)
    _clean_output(output)

    source_root = _source_root(resolved_params)
    failures: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    standard_paths: dict[str, str] = {}
    standard_notes: dict[str, list[str]] = {}
    attempted = 0
    normalization_stats = {"changed": 0, "controlRemoved": 0}
    records_path: Path | None = None
    records_root = Path(input_path).resolve()
    upstream: dict[str, Any] | None = None

    try:
        records_path, records_root, upstream = readers.locate_records(input_path)
    except readers.RecordsNotFound as exc:
        failures.append(
            {"id": "input", "reasonCode": "RECORDS_NOT_FOUND", "detail": str(exc)}
        )
        attempted = 1
    except (OSError, ValueError) as exc:
        failures.append(
            {"id": "input", "reasonCode": "INPUT_INVALID", "detail": f"{type(exc).__name__}: {exc}"}
        )
        attempted = 1

    if records_path is not None:
        timeout = int(cfg["limits"]["ffmpegTimeoutSec"])
        for number, raw_record, error in readers.iter_records(
            records_path, int(cfg["limits"]["maxRecords"])
        ):
            attempted += 1
            if error:
                failures.append(
                    {"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": error}
                )
                continue
            assert raw_record is not None
            errors = schema.validate_record(raw_record)
            partitions = raw_record.get("partitions") or {}
            if not errors and (
                partitions.get("modal") != raw_record.get("modal")
                or partitions.get("source") != raw_record.get("source")
            ):
                errors.append("partitions.modal/source 与记录头不一致")
            if errors:
                failures.append(
                    {
                        "id": raw_record.get("record_id") or f"line:{number}",
                        "reasonCode": "RECORD_SCHEMA_INVALID",
                        "detail": "; ".join(errors),
                    }
                )
                continue

            record = json.loads(json.dumps(raw_record, ensure_ascii=False))
            normalized, stats = schema.normalize_text(record.get("text"))
            record["text"] = normalized
            quality = record.setdefault("quality", {})
            quality["emptyText"] = not (normalized or "").strip() if normalized is not None else True
            hashes = record.setdefault("hashes", {})
            if normalized is not None:
                hashes["simhash"] = simhash64(normalized)
            metadata = record.setdefault("metadata", {})
            extra = metadata.setdefault("extra", {})
            extra["normalization"] = stats
            extra["textSha256"] = (
                hashlib.sha256((normalized or "").encode("utf-8")).hexdigest()
                if normalized is not None
                else None
            )
            if stats["changed"]:
                normalization_stats["changed"] += 1
            normalization_stats["controlRemoved"] += int(stats["removedControlChars"])

            standard_rel, notes, failure_reason = _standardize(
                record, records_root, source_root, output, cfg, timeout
            )
            extra["standardizationNotes"] = notes
            if failure_reason:
                failures.append(
                    {
                        "id": record["record_id"],
                        "reasonCode": failure_reason.split(":", 1)[0],
                        "detail": failure_reason,
                    }
                )
                continue
            if standard_rel:
                standard_paths[record["record_id"]] = standard_rel
            standard_notes[record["record_id"]] = notes
            records.append(record)

    groups, duplicate_of, dedup_stats = dedup.find_duplicates(records, cfg)
    for record in records:
        extra = record["metadata"].setdefault("extra", {})
        if record["record_id"] in duplicate_of:
            extra["duplicateOf"] = duplicate_of[record["record_id"]]

    parquet_stats = _write_partitioned_parquet(
        records, output, standard_paths, duplicate_of, cfg
    )
    metadata_rows = index.build_metadata_rows(records, standard_paths, duplicate_of)
    index_stats = index.write_index(metadata_rows, output / "index")
    missing = index.missing_fields(records)

    anomalies: list[dict[str, Any]] = []
    for record in records:
        anomalies.extend(
            index.detect_anomalies(
                record,
                records_root=records_root,
                cfg=cfg,
                standardization_notes=standard_notes.get(record["record_id"], []),
            )
        )
    associations = index.build_associations(records, batch_label=records_root.name)
    partitions = index.partition_stats(records)

    records_out_path = output / "records.jsonl"
    duplicates_path = output / "duplicates.jsonl"
    anomalies_path = output / "anomalies.jsonl"
    associations_path = output / "associations.jsonl"
    failures_path = output / "failures.jsonl"
    input_manifest_path = output / "input_manifest.json"
    metrics_path = output / "metrics.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(records_out_path, records)
    write_jsonl(duplicates_path, groups)
    write_jsonl(anomalies_path, anomalies)
    write_jsonl(associations_path, associations)
    write_jsonl(failures_path, failures)
    write_json(output / "index" / "missing_fields.json", missing)
    write_json(output / "index" / "partition_stats.json", partitions)

    if records_path is not None:
        fingerprint, records_bytes = fingerprint_file(records_path)
    else:
        fingerprint = hashlib.sha256(f"missing-records:{records_root}".encode("utf-8")).hexdigest()
        records_bytes = 0
    input_bytes = sum(int((record.get("metadata") or {}).get("sizeBytes") or 0) for record in records)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix() if records_path else None,
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "sourceRoot": source_root.as_posix() if source_root else None,
            "upstreamManifest": {
                "operatorId": (upstream or {}).get("operatorId"),
                "runId": (upstream or {}).get("runId"),
                "operatorVersion": (upstream or {}).get("operatorVersion"),
                "sampleCount": (upstream or {}).get("sampleCount"),
                "successCount": (upstream or {}).get("successCount"),
                "failedCount": (upstream or {}).get("failedCount"),
            },
            "note": "recordsFingerprint 只覆盖 result.jsonl；源文件按记录 sourcePath 定位。",
        },
    )

    decode_check = _decode_check(output, cfg)
    metrics = _build_metrics(
        records=records,
        failures=failures,
        attempted=attempted,
        dedup_stats=dedup_stats,
        parquet_stats=parquet_stats,
        index_stats=index_stats,
        missing=missing,
        anomalies=anomalies,
        associations=associations,
        partitions=partitions,
        normalization_stats=normalization_stats,
        decode_check=decode_check,
        upstream=upstream,
        cfg=cfg,
    )
    write_json(metrics_path, metrics)

    payload_artifacts = _collect_artifacts(
        output, exclude={"manifest.json", "summary.json", "result.json", "error.log"}
    )
    output_bytes = sum(item["bytes"] for item in payload_artifacts)
    manifest = {
        "runId": _run_id(fingerprint, resolved_params, resolved_seed),
        "inputFingerprint": f"sha256:{fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": (upstream or {}).get("modelVersion"),
        "treeVersion": (upstream or {}).get("treeVersion"),
        "paramsHash": f"sha256:{params_hash(resolved_params)}",
        "seed": resolved_seed,
        "sampleCount": attempted,
        "successCount": len(records),
        "failedCount": len(failures),
        "inputBytes": input_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / input_bytes, 6) if input_bytes else 0.0,
        "artifacts": payload_artifacts,
        "failedSamples": failures[: int(cfg["limits"]["maxFailuresInResult"])],
        "createdAt": _now_iso(),
        "notes": [
            "modelVersion/treeVersion 沿用上游 manifest；无上游时为空，不编造。",
            "inputBytes 为上游记录 sizeBytes 合计；outputBytes 为本次产物合计。",
            "重复记录保留原记录并写 duplicateOf，下游按策略筛选。",
            "视频转码使用 ffmpeg libx264；编码器不可用时流复制并写 STANDARDIZATION_FALLBACK。",
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
        "sampleCount": attempted,
        "successCount": len(records),
        "failedCount": len(failures),
        "metrics": metrics,
        "provisional": True,
        "generatedAt": _now_iso(),
    }
    write_json(summary_path, summary)

    artifacts = _collect_artifacts(output, exclude={"result.json", "error.log"})
    return {
        "modelVersion": manifest["modelVersion"],
        "treeVersion": manifest["treeVersion"],
        "sampleCount": attempted,
        "successCount": len(records),
        "failedCount": len(failures),
        "failedSamples": failures[: int(cfg["limits"]["maxFailuresInResult"])],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": records_out_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "标准产物从上游记录与真实源文件生成；源文件缺失时记 SOURCE_FILE_MISSING，不伪造产物。",
            "未接入人工标注，不产出准确率/去重准确率等效果指标。",
        ],
    }


def _apply_param_overrides(cfg: dict[str, Any], params: dict[str, Any]) -> None:
    if "simhash_max_distance" in params:
        cfg["dedup"]["simhashMaxDistance"] = max(0, min(64, int(params["simhash_max_distance"])))
    if "phash_max_distance" in params:
        cfg["dedup"]["phashMaxDistance"] = max(0, min(64, int(params["phash_max_distance"])))
    if "max_records" in params:
        cfg["limits"]["maxRecords"] = max(1, int(params["max_records"]))


def _source_root(params: dict[str, Any]) -> Path | None:
    raw = params.get("source_root")
    if not raw:
        return None
    candidate = Path(str(raw))
    if candidate.is_absolute() and candidate.is_dir():
        return candidate.resolve()
    return None


def _standardize(
    record: dict[str, Any],
    records_root: Path,
    source_root: Path | None,
    output: Path,
    cfg: dict[str, Any],
    timeout: int,
) -> tuple[str | None, list[str], str | None]:
    modal = record["modal"]
    record_id = record["record_id"]
    if modal == "text":
        return None, ["TEXT_STANDARDIZED_TO_PARQUET"], None

    source = readers.resolve_source(record, records_root, source_root)
    if source is None:
        return None, [], "SOURCE_FILE_MISSING: 记录未指向可读源文件"

    try:
        if modal == "image":
            destination = output / "standard" / "images" / f"{record_id}.webp"
            standardized, notes = writer.standardize_image(source, destination, cfg)
        elif modal == "audio":
            destination = output / "standard" / "audio" / f"{record_id}.wav"
            standardized, notes = writer.standardize_audio(source, destination, cfg, timeout)
        else:
            destination = output / "standard" / "video" / f"{record_id}.mp4"
            standardized, notes = writer.standardize_video(source, destination, cfg, timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        return None, [], f"STANDARDIZATION_FAILED: {type(exc).__name__}: {exc}"
    return relative_posix(standardized, output), notes, None


def _write_partitioned_parquet(
    records: list[dict[str, Any]],
    output: Path,
    standard_paths: dict[str, str],
    duplicate_of: dict[str, str],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    partition_cfg = cfg["partition"]
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        parts = record["partitions"]
        key = (parts["modal"], parts["source"], parts["dt"])
        grouped.setdefault(key, []).append(record)

    files: list[dict[str, Any]] = []
    total_rows = 0
    for (modal, source, dt), items in sorted(grouped.items()):
        path = (
            output
            / "standard"
            / "parquet"
            / f"modal={modal}"
            / f"source={source}"
            / f"dt={dt}"
            / "part-0000.parquet"
        )
        relative = relative_posix(path, output)
        for record in items:
            standard_paths.setdefault(record["record_id"], relative)
        rows = [
            _parquet_row(record, standard_paths.get(record["record_id"]), duplicate_of)
            for record in items
        ]
        rows_count = writer.write_parquet(
            rows,
            path,
            row_group_size=int(partition_cfg["rowGroupSize"]),
            compression=str(partition_cfg["compression"]),
        )
        read_back = len(writer.read_parquet_rows(path))
        if read_back != rows_count:
            raise RuntimeError(f"Parquet 回读条数不一致：写入 {rows_count}，回读 {read_back}")
        total_rows += rows_count
        files.append(
            {
                "path": relative,
                "rows": rows_count,
                "bytes": path.stat().st_size,
                "partition": {"modal": modal, "source": source, "dt": dt},
            }
        )
    return {"files": len(files), "rows": total_rows, "partitions": files}


def _parquet_row(
    record: dict[str, Any], standard_path: str | None, duplicate_of: dict[str, str]
) -> dict[str, Any]:
    metadata = record.get("metadata") or {}
    hashes = record.get("hashes") or {}
    return {
        "record_id": record["record_id"],
        "modal": record["modal"],
        "source": record["source"],
        "dt": record["partitions"]["dt"],
        "text": record.get("text"),
        "text_chars": len(record.get("text") or ""),
        "text_sha256": (metadata.get("extra") or {}).get("textSha256"),
        "format": metadata.get("format"),
        "size_bytes": int(metadata.get("sizeBytes") or 0),
        "md5": hashes.get("md5"),
        "sha256": hashes.get("sha256"),
        "simhash": hashes.get("simhash"),
        "phash": hashes.get("phash"),
        "standard_path": standard_path,
        "duplicate_of": duplicate_of.get(record["record_id"]),
        "quality_json": json.dumps(record.get("quality") or {}, ensure_ascii=False, sort_keys=True),
        "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    }


def _decode_check(output: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    media_files = sorted(
        [
            path
            for path in output.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".webp", ".wav", ".mp4"}
            and "standard" in path.parts
        ],
        key=lambda item: item.as_posix(),
    )
    ratio = float(cfg["limits"]["decodeCheckRatio"])
    sample_size = max(1, int(len(media_files) * ratio)) if media_files else 0
    sampled = media_files[:sample_size]
    failed: list[str] = []
    for path in sampled:
        try:
            if path.suffix.lower() == ".webp":
                from PIL import Image

                with Image.open(path) as image:
                    image.load()
            elif path.suffix.lower() == ".wav":
                with wave.open(str(path), "rb") as handle:
                    handle.readframes(min(1000, handle.getnframes()))
            else:
                completed = writer._run(
                    [writer.ffmpeg_exe(), "-v", "error", "-i", str(path), "-f", "null", "-"],
                    timeout=int(cfg["limits"]["ffmpegTimeoutSec"]),
                )
                if completed.returncode != 0:
                    failed.append(relative_posix(path, output) or path.name)
        except Exception:  # noqa: BLE001 - 抽检失败记录到清单
            failed.append(relative_posix(path, output) or path.name)
    return {
        "mediaFiles": len(media_files),
        "sampleRatio": ratio,
        "checked": len(sampled),
        "ok": len(sampled) - len(failed),
        "failed": failed,
    }


def _build_metrics(
    *,
    records: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    attempted: int,
    dedup_stats: dict[str, Any],
    parquet_stats: dict[str, Any],
    index_stats: dict[str, Any],
    missing: dict[str, Any],
    anomalies: list[dict[str, Any]],
    associations: list[dict[str, Any]],
    partitions: dict[str, Any],
    normalization_stats: dict[str, Any],
    decode_check: dict[str, Any],
    upstream: dict[str, Any] | None,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    modal_counts = Counter(record["modal"] for record in records)
    source_counts = Counter(record["source"] for record in records)
    anomaly_counts = Counter(item["type"] for item in anomalies)
    failure_counts = Counter(item["reasonCode"] for item in failures)
    standardized = {
        "images": sum(1 for record in records if record["modal"] == "image"),
        "audio": sum(1 for record in records if record["modal"] == "audio"),
        "video": sum(1 for record in records if record["modal"] == "video"),
        "text": sum(1 for record in records if record["modal"] == "text"),
    }
    return {
        "sampleCount": attempted,
        "successCount": len(records),
        "recordCount": len(records),
        "failedCount": len(failures),
        "failureRate": round(len(failures) / attempted, 6) if attempted else 0.0,
        "modalCounts": dict(sorted(modal_counts.items())),
        "sourceCounts": dict(sorted(source_counts.items())),
        "standardized": standardized,
        "parquet": {
            "files": parquet_stats["files"],
            "rows": parquet_stats["rows"],
            "partitions": len(partitions),
            "compression": cfg["partition"]["compression"],
        },
        "index": {"rows": index_stats["rows"], "missingFields": missing},
        "dedup": dedup_stats,
        "anomalies": dict(sorted(anomaly_counts.items())),
        "associations": {
            "fileGroups": sum(1 for item in associations if item["level"] == "file"),
            "archiveGroups": sum(1 for item in associations if item["level"] == "archive"),
            "directoryGroups": sum(1 for item in associations if item["level"] == "directory"),
            "multiModalGroups": sum(1 for item in associations if len(item["modalities"]) > 1),
            "derivedStreamGroups": sum(1 for item in associations if item.get("hasDerivedStream")),
        },
        "normalization": normalization_stats,
        "decodeCheck": decode_check,
        "partitions": partitions,
        "failuresByReason": dict(sorted(failure_counts.items())),
        "upstream": {
            "operatorId": (upstream or {}).get("operatorId"),
            "runId": (upstream or {}).get("runId"),
            "sampleCount": (upstream or {}).get("sampleCount"),
            "successCount": (upstream or {}).get("successCount"),
            "failedCount": (upstream or {}).get("failedCount"),
            "countsMatch": (
                upstream is None
                or int(upstream.get("successCount") or 0) == attempted
                or int(upstream.get("sampleCount") or 0) == attempted
            ),
        },
        "config": {
            "normalizeVersion": cfg.get("version"),
            "thresholdsStatus": cfg.get("status"),
            "simhashMaxDistance": cfg["dedup"]["simhashMaxDistance"],
            "phashMaxDistance": cfg["dedup"]["phashMaxDistance"],
        },
        "provisional": True,
        "generatedAt": _now_iso(),
    }


def _collect_artifacts(output: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*"), key=lambda item: item.relative_to(output).as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in exclude:
            continue
        suffix = path.suffix.lower()
        artifact_type = {
            ".jsonl": "jsonl",
            ".json": "json",
            ".parquet": "parquet",
            ".webp": "image",
            ".wav": "audio",
            ".mp4": "video",
        }.get(suffix, "file")
        artifacts.append(
            {
                "type": artifact_type,
                "path": path.as_posix(),
                "sha256": file_hashes(path)[1],
                "bytes": path.stat().st_size,
            }
        )
    return artifacts


def _clean_output(output: Path) -> None:
    for name in (
        "records.jsonl",
        "duplicates.jsonl",
        "anomalies.jsonl",
        "associations.jsonl",
        "failures.jsonl",
        "input_manifest.json",
        "metrics.json",
        "manifest.json",
        "summary.json",
    ):
        (output / name).unlink(missing_ok=True)
    for name in ("standard", "index"):
        shutil.rmtree(output / name, ignore_errors=True)


def _run_id(fingerprint: str, params: dict[str, Any], seed: int) -> str:
    return hashlib.sha256(
        f"{fingerprint}|{OPERATOR_VERSION}|{params_hash(params)}|{seed}".encode("utf-8")
    ).hexdigest()[:16]


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
