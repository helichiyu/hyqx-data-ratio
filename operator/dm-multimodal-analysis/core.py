"""OP-01 多模态识别与解析（``corpus_ingest_multimodal_parse_v1``）。

流程：扫描输入 → 模态判定（扩展名+魔数+容器）→ 分模态解析 → 标准记录/失败/拆流清单
→ manifest/metrics/输入清单。所有指标来自真实解码与统计；OCR/ASR 后端缺失时如实
标注 ``unavailable``，不生成文本。算子不依赖 FastAPI/HTTP，不 import 其它算子。
"""

from __future__ import annotations

import mimetypes
import shutil
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import detect, media, records, source, textparse
from .utils.common import (
    compute_run_id,
    ensure_output_dir,
    fingerprint_input,
    load_config,
    now_iso,
    params_hash,
    safe_extract_zip,
    ts_to_dt,
    write_json,
    write_jsonl,
)
from .utils.hashes import bytes_hashes, file_hashes, phash64, simhash64

OPERATOR_ID = "dm-multimodal-analysis"
SEMANTIC_CODE = "corpus_ingest_multimodal_parse_v1"
OPERATOR_VERSION = "0.1.0"
DEFAULT_SEED = 42
MAX_FAILURES_IN_RESULT = 200


def run(
    input_path: str,
    params: dict | None = None,
    seed: int | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """执行解析；返回结果信封的业务字段（协议字段由 HTTP 层兜底）。"""

    cfg = load_config("parse.json")
    formats = load_config("formats.json")
    resolved_params = dict(params or {})
    resolved_seed = DEFAULT_SEED if seed is None else int(seed)
    _apply_param_overrides(cfg, resolved_params)

    output = ensure_output_dir(output_dir)
    _clean_output(output)
    root = Path(input_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"输入路径不存在：{root}")

    scan = _scan_inputs(root, output, formats, cfg)
    fingerprint, input_bytes = fingerprint_input(
        root, [(member["rel"], member["path"]) for member in scan["members"]]
    )
    param_digest = params_hash(resolved_params)
    run_id = compute_run_id(fingerprint, OPERATOR_VERSION, param_digest, resolved_seed)

    records_out: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = list(scan["failures"])
    split_entries: list[dict[str, Any]] = list(scan["archives"])
    attempted = len(scan["failures"])
    text_stats = {
        "records": 0,
        "empty": 0,
        "mojibakeWarnings": 0,
        "decodeFailures": 0,
    }
    detection_stats = {"lowConfidence": 0, "conflicts": 0, "byModal": Counter()}
    pdf_stats = {"documents": 0, "pages": 0, "scannedPages": 0, "emptyPages": 0}
    media_stats = {
        "images": 0,
        "audioFiles": 0,
        "silentAudio": 0,
        "videoFiles": 0,
        "videosWithAudio": 0,
        "keyframes": 0,
    }

    for member in scan["members"]:
        rel = member["rel"]
        path: Path = member["path"]
        archive = member["archive"]
        size_bytes = path.stat().st_size
        detection = detect.detect(path)
        split_entry: dict[str, Any] = {
            "path": rel,
            "archive": archive,
            "bytes": size_bytes,
            "format": detection["format"],
            "modal": detection["modal"],
            "confidence": detection["confidence"],
            "evidence": detection["evidence"],
            "streams": [],
        }

        if detection["modal"] is None:
            attempted += 1
            failures.append(
                {
                    "id": rel,
                    "reasonCode": "MODAL_UNKNOWN",
                    "detail": f"扩展名 {path.suffix or '(无)'} 与文件头均无法识别模态",
                }
            )
            split_entries.append(split_entry)
            continue
        if detection["confidence"] < float(cfg["detect"]["minConfidence"]):
            detection_stats["lowConfidence"] += 1
        if detection["conflicts"]:
            detection_stats["conflicts"] += 1
        detection_stats["byModal"][detection["modal"]] += 1

        try:
            if detection["modal"] == "text":
                produced, failed, entry_pdf = _parse_text_member(
                    rel, path, detection, cfg, resolved_params, split_entry
                )
                attempted += len(produced) + len(failed)
                failures.extend(failed)
                records_out.extend(produced)
                for record in produced:
                    stats = record["quality"]
                    text_stats["records"] += 1
                    if stats.get("emptyText"):
                        text_stats["empty"] += 1
                    if float(stats.get("mojibakeRate") or 0) > float(
                        cfg["text"]["mojibakeRateWarn"]
                    ):
                        text_stats["mojibakeWarnings"] += 1
                    if stats.get("decodeError"):
                        text_stats["decodeFailures"] += 1
                if entry_pdf:
                    pdf_stats["documents"] += 1
                    pdf_stats["pages"] += entry_pdf["pageCount"]
                    pdf_stats["scannedPages"] += len(entry_pdf["scannedPages"])
                    pdf_stats["emptyPages"] += len(entry_pdf["emptyPages"])
            elif detection["modal"] == "image":
                attempted += 1
                record, failure = _parse_image_member(
                    rel, path, detection, cfg, resolved_params, split_entry
                )
                if record:
                    records_out.append(record)
                    media_stats["images"] += 1
                if failure:
                    failures.append(failure)
            elif detection["modal"] == "audio":
                attempted += 1
                record, failure = _parse_audio_member(
                    rel, path, detection, cfg, resolved_params, split_entry, output
                )
                if record:
                    records_out.append(record)
                    media_stats["audioFiles"] += 1
                    if _is_silent(record):
                        media_stats["silentAudio"] += 1
                if failure:
                    failures.append(failure)
            else:  # video
                attempted += 1
                produced, failed, audio_units = _parse_video_member(
                    rel, path, detection, cfg, resolved_params, split_entry, output
                )
                records_out.extend(produced)
                failures.extend(failed)
                attempted += audio_units["attempted"]
                if audio_units["audioRecord"]:
                    records_out.append(audio_units["audioRecord"])
                    media_stats["audioFiles"] += 1
                if audio_units["failure"]:
                    failures.append(audio_units["failure"])
                if produced:
                    media_stats["videoFiles"] += 1
                    media_stats["keyframes"] += int(
                        produced[0]["metadata"].get("extra", {}).get("keyframeCount") or 0
                    )
                    if produced[0]["metadata"].get("extra", {}).get("hasAudio"):
                        media_stats["videosWithAudio"] += 1
        except Exception as exc:  # noqa: BLE001 - 单文件失败不拖垮整批
            attempted += 1
            failures.append(
                {
                    "id": rel,
                    "reasonCode": _reason_for_exception(exc),
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
        split_entries.append(split_entry)

    for record in records_out:
        errors = records.validate_record(record)
        if errors:
            failures.append(
                {
                    "id": record.get("record_id", "unknown"),
                    "reasonCode": "RECORD_SCHEMA_INVALID",
                    "detail": "; ".join(errors),
                }
            )

    result_path = output / "result.jsonl"
    failures_path = output / "failures.jsonl"
    split_path = output / "split_manifest.json"
    input_manifest_path = output / "input_manifest.json"
    metrics_path = output / "metrics.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, records_out)
    write_jsonl(failures_path, failures)
    write_json(split_path, {"entries": split_entries, "generatedAt": now_iso()})
    write_json(
        input_manifest_path,
        {
            "inputPath": root.as_posix(),
            "inputFingerprint": f"sha256:{fingerprint}",
            "members": [
                {
                    "path": member["rel"],
                    "bytes": member["path"].stat().st_size,
                    "sha256": file_hashes(member["path"])[1],
                    "archive": member["archive"],
                }
                for member in scan["members"]
            ],
            "skipped": scan["skipped"],
            "note": "zip 输入按展开后的成员计算指纹；HTTP 层 runId 按压缩包计算，二者在 result 中分别可见。",
        },
    )

    metrics = _build_metrics(
        cfg=cfg,
        formats=formats,
        members=scan["members"],
        records_out=records_out,
        failures=failures,
        attempted=attempted,
        text_stats=text_stats,
        detection_stats=detection_stats,
        pdf_stats=pdf_stats,
        media_stats=media_stats,
        split_entries=split_entries,
    )
    write_json(metrics_path, metrics)

    payload_artifacts = _collect_artifacts(
        output,
        exclude={"manifest.json", "summary.json", "result.json", "error.log"},
    )
    output_bytes = sum(item["bytes"] for item in payload_artifacts)
    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": None,
        "paramsHash": f"sha256:{param_digest}",
        "seed": resolved_seed,
        "sampleCount": attempted,
        "successCount": len(records_out),
        "failedCount": len(failures),
        "inputBytes": input_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / input_bytes, 6) if input_bytes else 0.0,
        "artifacts": payload_artifacts,
        "failedSamples": failures[:MAX_FAILURES_IN_RESULT],
        "createdAt": now_iso(),
        "notes": [
            "modelVersion=null：OP-01 为规则/解析实现，未加载模型权重。",
            "treeVersion=null：本算子不消费分类树。",
            "outputBytes/compressionRatio 统计 payload 产物，不含 manifest/summary 自身。",
            "分区 dt 默认取文件修改时间（file_time），业务口径待人工确认。",
            "OCR 后端未提供：扫描页记 scannedPages 并标 OCR_BACKEND_UNAVAILABLE。",
        ],
    }
    write_json(manifest_path, manifest)

    summary = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "runId": run_id,
        "inputFingerprint": f"sha256:{fingerprint}",
        "paramsHash": f"sha256:{param_digest}",
        "seed": resolved_seed,
        "sampleCount": attempted,
        "successCount": len(records_out),
        "failedCount": len(failures),
        "metrics": metrics,
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(summary_path, summary)

    artifacts = _collect_artifacts(output, exclude={"result.json", "error.log"})
    return {
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": attempted,
        "successCount": len(records_out),
        "failedCount": len(failures),
        "failedSamples": failures[:MAX_FAILURES_IN_RESULT],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "解析指标来自真实样例与真实解码统计；无人工标注，不产出效果准确率。",
            "OCR/ASR 模型未接入，相关能力标注 unavailable。",
        ],
    }


def _apply_param_overrides(cfg: dict[str, Any], params: dict[str, Any]) -> None:
    if "max_keyframes" in params:
        cfg["limits"]["maxKeyframes"] = max(1, min(240, int(params["max_keyframes"])))
    if "extract_audio" in params:
        cfg["video"]["extractAudioStream"] = bool(params["extract_audio"])
    if "ocr_enabled" in params:
        cfg["pdf"]["ocrEnabled"] = bool(params["ocr_enabled"])
    if "max_file_bytes" in params:
        cfg["limits"]["maxFileBytes"] = max(1, int(params["max_file_bytes"]))
    dt_source = params.get("dt_source")
    if dt_source in cfg["dt"]["allowedSources"]:
        cfg["dt"]["defaultSource"] = dt_source


def _scan_inputs(
    root: Path, output: Path, formats: dict[str, Any], cfg: dict[str, Any]
) -> dict[str, Any]:
    limits = cfg["limits"]
    allowed = detect.supported_suffixes()
    members: list[dict[str, Any]] = []
    archives: list[dict[str, Any]] = []
    skipped: list[str] = []
    failures: list[dict[str, Any]] = []

    def expand_archive(archive_path: Path, rel_prefix: str) -> None:
        destination = output / "_input_extracted" / _safe_component(rel_prefix)
        try:
            extracted, skipped_members = safe_extract_zip(
                archive_path,
                destination,
                allowed,
                max_members=int(limits["maxZipMembers"]),
                max_bytes=int(limits["maxZipExtractBytes"]),
            )
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            failures.append(
                {
                    "id": rel_prefix,
                    "reasonCode": "ZIP_INVALID",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            return
        membership = []
        for item in extracted:
            rel = f"{rel_prefix}/{item.name}"
            membership.append(rel)
            members.append({"rel": rel, "path": item, "archive": archive_path.name})
        archives.append(
            {
                "path": rel_prefix,
                "kind": "archive",
                "bytes": archive_path.stat().st_size,
                "members": membership,
                "skipped": skipped_members,
            }
        )
        if not extracted:
            failures.append(
                {
                    "id": rel_prefix,
                    "reasonCode": "ZIP_EMPTY",
                    "detail": "zip 内没有白名单允许的文件",
                }
            )

    if root.is_file():
        if root.suffix.lower() in set(formats["archives"]):
            expand_archive(root, root.name)
        else:
            members.append({"rel": root.name, "path": root, "archive": None})
        return {
            "members": members,
            "archives": archives,
            "skipped": skipped,
            "failures": failures,
        }

    for item in sorted(root.rglob("*"), key=lambda path: path.as_posix()):
        rel = item.relative_to(root).as_posix()
        if item.is_symlink():
            skipped.append(f"{rel}（符号链接）")
            continue
        if not item.is_file():
            continue
        suffix = item.suffix.lower()
        if suffix in set(formats["archives"]):
            expand_archive(item, rel)
        elif suffix in allowed:
            members.append({"rel": rel, "path": item, "archive": None})
        else:
            failures.append(
                {
                    "id": rel,
                    "reasonCode": "UNSUPPORTED_FILE_TYPE",
                    "detail": f"后缀 {suffix or '(无)'} 不在四模态白名单",
                }
            )
    return {"members": members, "archives": archives, "skipped": skipped, "failures": failures}


def _parse_text_member(
    rel: str,
    path: Path,
    detection: dict[str, Any],
    cfg: dict[str, Any],
    params: dict[str, Any],
    split_entry: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    max_chars = int(cfg["limits"]["maxTextChars"])
    pdf_entry = None
    if detection["format"] == "pdf" or path.suffix.lower() == ".pdf":
        parsed = textparse.parse_pdf(path, cfg, max_chars=max_chars)
        pdf_entry = parsed
        units = [
            {
                "text": parsed["text"],
                "line": 1,
                "fields": [],
                "fileStats": parsed["fileStats"],
                "truncated": parsed["truncated"],
                "capturedAt": parsed["capturedAt"],
                "pdf": {
                    "pageCount": parsed["pageCount"],
                    "scannedPages": parsed["scannedPages"][:200],
                    "emptyPages": parsed["emptyPages"][:200],
                    "blockPages": parsed["blockPages"],
                    "fontSizes": parsed["fontSizes"],
                    "ocrStatus": "unavailable" if parsed["scannedPages"] else "not_required",
                    "ocrAttempted": 0,
                },
            }
        ]
        failures: list[dict[str, Any]] = []
        split_entry["streams"].append(
            {
                "modal": "text",
                "type": "pdf_document",
                "pages": parsed["pageCount"],
                "scannedPages": len(parsed["scannedPages"]),
                "ocrStatus": "unavailable" if parsed["scannedPages"] else "not_required",
            }
        )
    else:
        parsed = textparse.parse_text_file(path, cfg, max_chars=max_chars)
        units = [
            {
                "text": item["text"],
                "line": item["line"],
                "fields": item.get("fields", []),
                "fileStats": parsed["fileStats"],
                "truncated": item.get("truncated", False),
                "capturedAt": None,
                "pdf": None,
            }
            for item in parsed["records"]
        ]
        failures = [
            {
                "id": f"{rel}#{item['id']}",
                "reasonCode": item["reasonCode"],
                "detail": item.get("detail"),
            }
            for item in parsed["failures"]
        ]
        split_entry["streams"].append(
            {"modal": "text", "type": "text_unit", "units": len(units) + len(failures)}
        )

    produced: list[dict[str, Any]] = []
    file_md5, file_sha = file_hashes(path)
    for unit in units:
        text = unit["text"]
        lines = unit["line"]
        content_sha = file_sha
        content_md5 = file_md5
        content_bytes = path.stat().st_size
        if path.suffix.lower() == ".jsonl" and text is not None:
            payload = text.encode("utf-8")
            content_md5, content_sha = bytes_hashes(payload)
            content_bytes = len(payload)
        record_id = (
            records.record_id_for_file(rel, content_sha)
            if len(units) == 1 and path.suffix.lower() != ".jsonl"
            else records.record_id_for_text(f"{rel}\0{lines}\0{text}")
        )
        source_result = source.classify(
            path,
            text=text,
            fields=unit["fields"],
            format_name=detection["format"],
        )
        dt, dt_source = _resolve_dt(path, cfg, params, unit["capturedAt"])
        stats = unit["fileStats"]
        unit_text_stats = textparse.analyze_text(text or "")
        decode_error = stats.get("decodeError")
        notes: list[str] = []
        if unit.get("truncated"):
            notes.append("TEXT_TRUNCATED")
        if unit["pdf"] and unit["pdf"]["ocrStatus"] == "unavailable":
            notes.append("OCR_BACKEND_UNAVAILABLE")
        if decode_error:
            notes.append(str(decode_error))
        if unit_text_stats["empty"]:
            notes.append("EMPTY_TEXT")

        extra: dict[str, Any] = {
            "file": rel,
            "sourcePath": path.resolve().as_posix(),
            "fileBytes": path.stat().st_size,
            "line": lines,
            "encoding": stats.get("encoding"),
            "detection": {
                "modal": detection["modal"],
                "confidence": detection["confidence"],
                "evidence": detection["evidence"],
                "conflicts": detection["conflicts"],
            },
            "sourceEvidence": source_result["evidence"],
            "sourceScores": source_result["scores"],
            "sourceClassVersion": source_result["sourceClassVersion"],
            "dtSource": dt_source,
        }
        if unit["pdf"]:
            extra["pdf"] = unit["pdf"]
        record = records.make_record(
            record_id=record_id,
            modal="text",
            source=source_result["source"],
            text=text,
            metadata={
                "format": detection["format"],
                "mime": mimetypes.guess_type(path.name)[0]
                or ("application/pdf" if detection["format"] == "pdf" else "text/plain"),
                "sizeBytes": content_bytes,
                "sha256": content_sha,
                "md5": content_md5,
                "capturedAt": unit["capturedAt"],
                "originalSource": rel,
                "synthetic": False,
                "extra": extra,
            },
            quality={
                "decodable": decode_error != "DECODE_FAILED",
                "completeness": float(stats.get("completeness", 1.0)),
                "emptyText": bool(unit_text_stats["empty"]),
                "mojibakeRate": float(unit_text_stats["mojibakeRate"]),
                "decodeError": decode_error,
                "notes": notes,
            },
            partitions={"modal": "text", "source": source_result["source"], "dt": dt},
            hashes={
                "md5": content_md5,
                "sha256": content_sha,
                "simhash": simhash64(text or ""),
                "phash": None,
            },
        )
        produced.append(record)
    return produced, failures, pdf_entry


def _parse_image_member(
    rel: str,
    path: Path,
    detection: dict[str, Any],
    cfg: dict[str, Any],
    params: dict[str, Any],
    split_entry: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    info = media.image_info(path)
    split_entry["streams"].append(
        {
            "modal": "image",
            "type": "image",
            "decodable": info["decodable"],
            "width": info.get("width"),
            "height": info.get("height"),
        }
    )
    if not info["decodable"]:
        return None, {
            "id": rel,
            "reasonCode": "DECODE_FAILED",
            "detail": info.get("decodeError"),
        }
    md5, sha = file_hashes(path)
    phash = None
    phash_error = None
    try:
        phash = phash64(path)
    except Exception as exc:  # noqa: BLE001 - pHash 失败不阻塞解析
        phash_error = f"{type(exc).__name__}: {exc}"
    source_result = source.classify(path, text=None, format_name=detection["format"])
    dt, dt_source = _resolve_dt(path, cfg, params, info.get("capturedAt"))
    notes = []
    if phash_error:
        notes.append(f"PHASH_FAILED: {phash_error}")
    record = records.make_record(
        record_id=records.record_id_for_file(rel, sha),
        modal="image",
        source=source_result["source"],
        text=None,
        metadata={
            "format": info.get("format") or detection["format"],
            "mime": info.get("mime") or mimetypes.guess_type(path.name)[0],
            "sizeBytes": path.stat().st_size,
            "sha256": sha,
            "md5": md5,
            "width": info["width"],
            "height": info["height"],
            "capturedAt": info.get("capturedAt"),
            "originalSource": rel,
            "synthetic": False,
            "extra": {
                "file": rel,
                "sourcePath": path.resolve().as_posix(),
                "mode": info.get("mode"),
                "dpi": info.get("dpi"),
                "hasIcc": info.get("hasIcc"),
                "exif": info.get("exif"),
                "detection": {
                    "modal": detection["modal"],
                    "confidence": detection["confidence"],
                    "evidence": detection["evidence"],
                },
                "sourceEvidence": source_result["evidence"],
                "sourceScores": source_result["scores"],
                "dtSource": dt_source,
            },
        },
        quality={
            "decodable": True,
            "completeness": 1.0,
            "emptyText": False,
            "mojibakeRate": 0.0,
            "decodeError": None,
            "notes": notes,
        },
        partitions={"modal": "image", "source": source_result["source"], "dt": dt},
        hashes={"md5": md5, "sha256": sha, "simhash": None, "phash": phash},
    )
    return record, None


def _parse_audio_member(
    rel: str,
    path: Path,
    detection: dict[str, Any],
    cfg: dict[str, Any],
    params: dict[str, Any],
    split_entry: dict[str, Any],
    output: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    md5, sha = file_hashes(path)
    record_id = records.record_id_for_file(rel, sha)
    try:
        info = media.audio_info(
            path,
            cfg,
            work_dir=output / "streams" / "audio",
            stem=record_id,
            decode=True,
        )
    except media.NoAudioStream as exc:
        return None, {"id": rel, "reasonCode": "NO_AUDIO_STREAM", "detail": str(exc)}
    except media.DependencyUnavailable as exc:
        return None, {"id": rel, "reasonCode": "DEPENDENCY_UNAVAILABLE", "detail": str(exc)}
    wav_path = info.get("wavPath")
    split_entry["streams"].append(
        {
            "modal": "audio",
            "type": "audio",
            "durationSec": info.get("durationSec"),
            "sampleRate": info.get("sampleRate"),
            "channels": info.get("channels"),
            "wav16k": _relative(wav_path, output) if wav_path else None,
        }
    )
    source_result = source.classify(path, text=None, format_name=detection["format"])
    dt, dt_source = _resolve_dt(path, cfg, params, None)
    notes = []
    if info.get("decodeError"):
        notes.append("AUDIO_DECODE_ERROR")
    vad = info.get("vad") or {}
    if vad.get("speechRatio") == 0:
        notes.append("NO_SPEECH_DETECTED")
    if info.get("truncatedDecode"):
        notes.append("AUDIO_DECODE_TRUNCATED")
    record = records.make_record(
        record_id=record_id,
        modal="audio",
        source=source_result["source"],
        text=None,
        metadata={
            "format": detection["format"],
            "mime": mimetypes.guess_type(path.name)[0],
            "sizeBytes": path.stat().st_size,
            "sha256": sha,
            "md5": md5,
            "durationSec": info.get("durationSec"),
            "sampleRate": info.get("sampleRate"),
            "channels": info.get("channels"),
            "capturedAt": None,
            "originalSource": rel,
            "synthetic": False,
            "extra": {
                "file": rel,
                "sourcePath": path.resolve().as_posix(),
                "codec": info.get("codec"),
                "bitrateKbps": info.get("bitrateKbps"),
                "vad": vad,
                "wav16k": _relative(wav_path, output) if wav_path else None,
                "decodeError": info.get("decodeError"),
                "detection": {
                    "modal": detection["modal"],
                    "confidence": detection["confidence"],
                    "evidence": detection["evidence"],
                },
                "sourceEvidence": source_result["evidence"],
                "sourceScores": source_result["scores"],
                "dtSource": dt_source,
            },
        },
        quality={
            "decodable": bool(wav_path),
            "completeness": 1.0,
            "emptyText": False,
            "mojibakeRate": 0.0,
            "decodeError": info.get("decodeError"),
            "notes": notes,
        },
        partitions={"modal": "audio", "source": source_result["source"], "dt": dt},
        hashes={"md5": md5, "sha256": sha, "simhash": None, "phash": None},
    )
    return record, None


def _parse_video_member(
    rel: str,
    path: Path,
    detection: dict[str, Any],
    cfg: dict[str, Any],
    params: dict[str, Any],
    split_entry: dict[str, Any],
    output: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    md5, sha = file_hashes(path)
    record_id = records.record_id_for_file(rel, sha)
    try:
        info = media.video_info(
            path, cfg, work_dir=output / "streams" / "video", record_id=record_id
        )
    except media.DependencyUnavailable as exc:
        return [], [{"id": rel, "reasonCode": "DEPENDENCY_UNAVAILABLE", "detail": str(exc)}], {
            "attempted": 0, "audioRecord": None, "failure": None
        }
    except Exception as exc:  # noqa: BLE001
        return [], [{"id": rel, "reasonCode": "DECODE_FAILED", "detail": f"{type(exc).__name__}: {exc}"}], {
            "attempted": 0, "audioRecord": None, "failure": None
        }

    keyframes = [
        {
            "index": item["index"],
            "tsSec": item["tsSec"],
            "path": _relative(item["path"], output),
        }
        for item in info["keyframes"]
    ]
    split_entry["streams"].append(
        {
            "modal": "video",
            "type": "video_stream",
            "codec": info.get("codec"),
            "width": info.get("width"),
            "height": info.get("height"),
            "fps": info.get("fps"),
            "durationSec": info.get("durationSec"),
            "keyframes": len(keyframes),
        }
    )
    source_result = source.classify(path, text=None, format_name=detection["format"])
    dt, dt_source = _resolve_dt(path, cfg, params, None)
    notes = []
    if info.get("keyframeError"):
        notes.append("KEYFRAME_EXTRACTION_FAILED")
    audio_stream = info.get("audio")
    record = records.make_record(
        record_id=record_id,
        modal="video",
        source=source_result["source"],
        text=None,
        metadata={
            "format": detection["format"],
            "mime": mimetypes.guess_type(path.name)[0],
            "sizeBytes": path.stat().st_size,
            "sha256": sha,
            "md5": md5,
            "width": info.get("width"),
            "height": info.get("height"),
            "durationSec": info.get("durationSec"),
            "fps": info.get("fps"),
            "frameCount": info.get("frameCount"),
            "capturedAt": None,
            "originalSource": rel,
            "synthetic": False,
            "extra": {
                "file": rel,
                "sourcePath": path.resolve().as_posix(),
                "codec": info.get("codec"),
                "bitrateKbps": info.get("bitrateKbps"),
                "frameCountSource": info.get("frameCountSource"),
                "hasAudio": info.get("hasAudio"),
                "audioStream": audio_stream,
                "keyframes": keyframes,
                "keyframeCount": len(keyframes),
                "keyframeError": info.get("keyframeError"),
                "audioWav16k": _relative(info.get("audioWavPath"), output)
                if info.get("audioWavPath")
                else None,
                "audioError": info.get("audioError"),
                "detection": {
                    "modal": detection["modal"],
                    "confidence": detection["confidence"],
                    "evidence": detection["evidence"],
                },
                "sourceEvidence": source_result["evidence"],
                "sourceScores": source_result["scores"],
                "dtSource": dt_source,
            },
        },
        quality={
            "decodable": True,
            "completeness": 1.0,
            "emptyText": False,
            "mojibakeRate": 0.0,
            "decodeError": None,
            "notes": notes,
        },
        partitions={"modal": "video", "source": source_result["source"], "dt": dt},
        hashes={"md5": md5, "sha256": sha, "simhash": None, "phash": None},
    )

    audio_units: dict[str, Any] = {"attempted": 0, "audioRecord": None, "failure": None}
    if info.get("hasAudio"):
        audio_units["attempted"] = 1
        wav_path = info.get("audioWavPath")
        if not wav_path:
            audio_units["failure"] = {
                "id": f"{rel}#audio",
                "reasonCode": "AUDIO_STREAM_EXTRACT_FAILED",
                "detail": (info.get("audioError") or "")[-500:],
            }
        else:
            try:
                audio_meta = media.audio_info(wav_path, cfg, decode=False)
            except (media.NoAudioStream, media.DependencyUnavailable) as exc:
                audio_units["failure"] = {
                    "id": f"{rel}#audio",
                    "reasonCode": "AUDIO_STREAM_PARSE_FAILED",
                    "detail": str(exc),
                }
            else:
                audio_sha = file_hashes(wav_path)[1]
                audio_record_id = records.record_id_for_file(f"{rel}#audio", audio_sha)
                split_entry["streams"].append(
                    {
                        "modal": "audio",
                        "type": "audio_stream",
                        "derivedFrom": record_id,
                        "durationSec": audio_meta.get("durationSec"),
                        "sampleRate": audio_meta.get("sampleRate"),
                        "wav16k": _relative(wav_path, output),
                    }
                )
                audio_units["audioRecord"] = records.make_record(
                    record_id=audio_record_id,
                    modal="audio",
                    source=source_result["source"],
                    text=None,
                    metadata={
                        "format": "wav",
                        "mime": "audio/wav",
                        "sizeBytes": wav_path.stat().st_size,
                        "sha256": audio_sha,
                        "md5": file_hashes(wav_path)[0],
                        "durationSec": audio_meta.get("durationSec"),
                        "sampleRate": audio_meta.get("sampleRate"),
                        "channels": audio_meta.get("channels"),
                        "capturedAt": None,
                        "originalSource": rel,
                        "synthetic": False,
                        "extra": {
                            "file": _relative(wav_path, output),
                            "sourcePath": wav_path.resolve().as_posix(),
                            "derivedFrom": record_id,
                            "vad": audio_meta.get("vad"),
                            "codec": audio_meta.get("codec"),
                            "dtSource": dt_source,
                        },
                    },
                    quality={
                        "decodable": True,
                        "completeness": 1.0,
                        "emptyText": False,
                        "mojibakeRate": 0.0,
                        "decodeError": None,
                        "notes": ["DERIVED_AUDIO_STREAM"],
                    },
                    partitions={"modal": "audio", "source": source_result["source"], "dt": dt},
                    hashes={
                        "md5": file_hashes(wav_path)[0],
                        "sha256": audio_sha,
                        "simhash": None,
                        "phash": None,
                    },
                )
    return [record], [], audio_units


def _build_metrics(
    *,
    cfg: dict[str, Any],
    formats: dict[str, Any],
    members: list[dict[str, Any]],
    records_out: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    attempted: int,
    text_stats: dict[str, Any],
    detection_stats: dict[str, Any],
    pdf_stats: dict[str, Any],
    media_stats: dict[str, Any],
    split_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    modal_counter = Counter(record["modal"] for record in records_out)
    source_counter = Counter(record["source"] for record in records_out)
    record_bytes = Counter()
    for record in records_out:
        record_bytes[record["modal"]] += int(record["metadata"].get("sizeBytes") or 0)
    input_bytes_by_modal = Counter()
    for member in members:
        detection = detect.detect(member["path"])
        input_bytes_by_modal[detection["modal"] or "unknown"] += member["path"].stat().st_size
    failure_reasons = Counter(item["reasonCode"] for item in failures)
    text_records = max(1, int(text_stats["records"]))
    return {
        "fileMembers": len(members),
        "archives": sum(1 for entry in split_entries if entry.get("kind") == "archive"),
        "sampleCount": attempted,
        "successCount": len(records_out),
        "recordCount": len(records_out),
        "failedCount": len(failures),
        "failureRate": round(len(failures) / attempted, 6) if attempted else 0.0,
        "modalCounts": dict(sorted(modal_counter.items())),
        "sourceCounts": dict(sorted(source_counter.items())),
        "recordBytesByModal": dict(sorted(record_bytes.items())),
        "inputBytesByModal": dict(sorted(input_bytes_by_modal.items())),
        "text": {
            "records": text_stats["records"],
            "emptyTextRecords": text_stats["empty"],
            "emptyTextRate": round(text_stats["empty"] / text_records, 6),
            "mojibakeWarnRecords": text_stats["mojibakeWarnings"],
            "mojibakeRate": round(text_stats["mojibakeWarnings"] / text_records, 6),
            "decodeFailureRecords": text_stats["decodeFailures"],
            "mojibakeWarnThreshold": float(cfg["text"]["mojibakeRateWarn"]),
        },
        "pdf": {
            **pdf_stats,
            "ocrStatus": "unavailable" if pdf_stats["scannedPages"] else "not_required",
            "ocrAttempted": 0,
            "ocrSucceeded": 0,
            "note": "未接入 OCR 后端；扫描页只统计不伪造文本。",
        },
        "media": media_stats,
        "detection": {
            "lowConfidenceFiles": detection_stats["lowConfidence"],
            "conflictFiles": detection_stats["conflicts"],
            "minConfidence": float(cfg["detect"]["minConfidence"]),
            "byModal": dict(sorted(detection_stats["byModal"].items())),
        },
        "failuresByReason": dict(sorted(failure_reasons.items())),
        "config": {
            "formatsVersion": formats.get("version"),
            "parseVersion": cfg.get("version"),
            "thresholdsStatus": cfg.get("status"),
            "dtSource": cfg["dt"]["defaultSource"],
            "maxKeyframes": int(cfg["limits"]["maxKeyframes"]),
        },
        "provisional": True,
        "generatedAt": now_iso(),
    }


def _collect_artifacts(output: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*"), key=lambda item: item.relative_to(output).as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in exclude or relative.startswith("_input_extracted/"):
            continue
        artifact_type = _artifact_type(path)
        artifacts.append(
            {
                "type": artifact_type,
                "path": path.as_posix(),
                "sha256": file_hashes(path)[1],
                "bytes": path.stat().st_size,
            }
        )
    return artifacts


def _artifact_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".jsonl": "jsonl",
        ".json": "json",
        ".wav": "audio",
        ".jpg": "keyframe",
        ".jpeg": "keyframe",
        ".png": "image",
    }
    return mapping.get(suffix, "file")


def _resolve_dt(
    path: Path, cfg: dict[str, Any], params: dict[str, Any], content_time: str | None
) -> tuple[str, str]:
    allowed = list(cfg["dt"]["allowedSources"])
    requested = params.get("dt_source") or cfg["dt"]["defaultSource"]
    dt_source = requested if requested in allowed else cfg["dt"]["defaultSource"]
    if dt_source == "content_time" and content_time:
        try:
            timestamp = datetime.fromisoformat(content_time).timestamp()
        except ValueError:
            timestamp = path.stat().st_mtime
            dt_source = "file_time"
        else:
            return ts_to_dt(timestamp), "content_time"
    if dt_source == "ingest_time":
        return ts_to_dt(datetime.now().timestamp()), "ingest_time"
    return ts_to_dt(path.stat().st_mtime), "file_time"


def _clean_output(output: Path) -> None:
    for name in (
        "result.jsonl",
        "failures.jsonl",
        "split_manifest.json",
        "input_manifest.json",
        "metrics.json",
        "manifest.json",
        "summary.json",
    ):
        (output / name).unlink(missing_ok=True)
    for name in ("streams", "_input_extracted"):
        shutil.rmtree(output / name, ignore_errors=True)


def _relative(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_component(value: str) -> str:
    cleaned = "".join(
        char if char.isalnum() or char in "._-" else "_" for char in value
    ).strip("._")
    return cleaned[:80] or "archive"


def _is_silent(record: dict[str, Any]) -> bool:
    vad = (record.get("metadata", {}).get("extra", {}) or {}).get("vad") or {}
    return float(vad.get("silenceRatio") or 0.0) >= 0.99


def _reason_for_exception(exc: Exception) -> str:
    if isinstance(exc, media.DependencyUnavailable):
        return "DEPENDENCY_UNAVAILABLE"
    if isinstance(exc, FileNotFoundError):
        return "INPUT_NOT_FOUND"
    return "PARSE_FAILED"
