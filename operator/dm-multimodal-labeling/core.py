"""OP-05 多模态自动打标（``corpus_label_multimodal_v1``）。

四模态统一零样本打标：文本原文 / 图像 OCR / 音频 ASR / 视频关键帧 OCR+音轨 ASR
→ bge 向量 → 内容树叶子标签余弦相似度 → softmax → topK → 阈值裁剪。
无证据或低置信进未归类池；无人工标注时不产出准确率。
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .utils import asr, embedder, labeler, ocr, tree, vision
from .utils.common import (
    DependencyUnavailable,
    ensure_output_dir,
    fingerprint_file,
    load_config,
    now_iso,
    params_hash,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-multimodal-labeling"
SEMANTIC_CODE = "corpus_label_multimodal_v1"
OPERATOR_VERSION = "0.1.0"
DEFAULT_SEED = 42
MAX_FAILURES = 500


def run(
    input_path: str,
    params: dict | None = None,
    seed: int | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    resolved_params = dict(params or {})
    resolved_seed = DEFAULT_SEED if seed is None else int(seed)
    _apply_overrides(cfg, resolved_params)
    output = ensure_output_dir(output_dir)
    _clean_output(output)

    records_path, records_root = _locate_records(input_path)
    standard_paths = _index_standard_paths(records_root)
    label_tree = tree.LabelTree(
        cfg,
        snapshot_path=_optional_text(resolved_params.get("tree_snapshot_path")),
        expected_version=_optional_text(resolved_params.get("tree_version")),
    )
    model = embedder.Embedder(cfg)
    label_matrix = labeler.build_label_matrix(model, label_tree, cfg)

    label_vectors_path = output / "label_vectors.npy"
    label_ids_path = output / "label_ids.jsonl"
    np.save(label_vectors_path, label_matrix.astype(np.float16))
    write_jsonl(
        label_ids_path,
        [
            {"row": index, **item}
            for index, item in enumerate(label_tree.labels)
        ],
    )

    records: list[dict[str, Any]] = []
    for number, record, error in _iter_records(records_path, int(cfg["limits"]["maxRecords"])):
        if error:
            records.append(
                {
                    "line": number,
                    "record": None,
                    "error": {"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": error},
                }
            )
        else:
            records.append({"line": number, "record": record, "error": None})

    derived_audio: dict[str, dict[str, Any]] = {}
    for item in records:
        record = item.get("record") or {}
        extra = (record.get("metadata") or {}).get("extra") or {}
        if record.get("modal") == "audio" and extra.get("derivedFrom"):
            derived_audio[str(extra["derivedFrom"])] = record

    result_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []
    tool_errors = Counter()
    modality_counts: Counter[str] = Counter()
    labeled_counts: Counter[str] = Counter()
    unclassified_counts: Counter[str] = Counter()
    confidence_sum: defaultdict[str, float] = defaultdict(float)
    evidence_chars: defaultdict[str, int] = defaultdict(int)

    invalid_label_count = 0
    for item in records:
        if item["error"]:
            failures.append(item["error"])
            result_rows.append(
                {
                    "record_id": item["error"]["id"],
                    "modal": None,
                    "labels": [],
                    "unclassified": True,
                    "reasonCode": item["error"]["reasonCode"],
                }
            )
            continue
        record = item["record"]
        record_id = str(record.get("record_id"))
        modal = str(record.get("modal"))
        modality_counts[modal] += 1
        try:
            outcome = _label_record(
                record,
                records_root,
                standard_paths,
                derived_audio,
                model,
                label_matrix,
                label_tree,
                cfg,
                output,
            )
        except (ocr.OcrFailed, asr.AsrFailed, vision.VisionFailed, DependencyUnavailable,
                FileNotFoundError) as exc:
            reason = {
                "OcrFailed": "OCR_FAILED",
                "AsrFailed": "ASR_FAILED",
                "VisionFailed": "KEYFRAME_FAILED",
                "DependencyUnavailable": "DEPENDENCY_UNAVAILABLE",
                "FileNotFoundError": "STANDARD_MEDIA_MISSING",
            }.get(type(exc).__name__, "LABELING_FAILED")
            tool_errors[reason] += 1
            failures.append({"id": record_id, "reasonCode": reason, "detail": str(exc)})
            result_rows.append(
                {
                    "record_id": record_id,
                    "modal": modal,
                    "labels": [],
                    "unclassified": True,
                    "reasonCode": reason,
                }
            )
            continue
        except Exception as exc:  # noqa: BLE001 - 单条失败不拖垮整批
            tool_errors["LABELING_FAILED"] += 1
            failures.append(
                {
                    "id": record_id,
                    "reasonCode": "LABELING_FAILED",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            result_rows.append(
                {
                    "record_id": record_id,
                    "modal": modal,
                    "labels": [],
                    "unclassified": True,
                    "reasonCode": "LABELING_FAILED",
                }
            )
            continue

        labels = outcome["labels"]
        for label in labels:
            if not label_tree.is_valid(label["path"]):
                label["pathValid"] = False
                invalid_label_count += 1
        row = {
            "record_id": record_id,
            "modal": modal,
            "labels": labels,
            "topK": outcome.get("topK", []),
            "unclassified": outcome["unclassified"],
            "reasonCode": outcome.get("reasonCode"),
            "top1": outcome.get("top1"),
            "margin": outcome.get("margin"),
            "evidence": outcome.get("evidence", {}),
        }
        result_rows.append(row)
        if labels:
            labeled_counts[modal] += 1
            confidence_sum[modal] += float(labels[0]["confidence"])
            evidence_chars[modal] += int(
                (outcome.get("evidence") or {}).get("chars") or 0
            )
        else:
            unclassified_counts[modal] += 1
            unclassified.append(
                {
                    "record_id": record_id,
                    "modal": modal,
                    "reasonCode": outcome.get("reasonCode"),
                    "topK": outcome.get("topK", []),
                    "evidence": outcome.get("evidence", {}),
                }
            )
            failures.append(
                {
                    "id": record_id,
                    "reasonCode": outcome.get("reasonCode") or "UNCLASSIFIED",
                    "detail": "未进入置信度阈值或缺少可识别文字/语音证据",
                }
            )

    result_path = output / "result.jsonl"
    unclassified_path = output / "unclassified.jsonl"
    failures_path = output / "failures.jsonl"
    input_manifest_path = output / "input_manifest.json"
    metrics_path = output / "metrics.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, result_rows)
    write_jsonl(unclassified_path, unclassified)
    write_jsonl(failures_path, failures)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "standardPaths": len(standard_paths),
            "note": "媒体内容取 OP-02 标准产物；文本取记录 text。",
        },
    )

    labeled_total = sum(labeled_counts.values())
    total = max(1, len(result_rows))
    metrics = {
        "modalityCounts": dict(sorted(modality_counts.items())),
        "labeledCounts": dict(sorted(labeled_counts.items())),
        "unclassifiedCounts": dict(sorted(unclassified_counts.items())),
        "labeledRate": round(labeled_total / total, 6),
        "meanConfidenceByModal": {
            modal: round(confidence_sum[modal] / labeled_counts[modal], 6)
            for modal in sorted(labeled_counts)
        },
        "meanEvidenceCharsByModal": {
            modal: round(evidence_chars[modal] / labeled_counts[modal], 3)
            for modal in sorted(labeled_counts)
        },
        "labelSpaceSize": len(label_tree.labels),
        "treeVersion": label_tree.tree_version,
        "treeHash": label_tree.tree_hash,
        "modelVersion": model.model_version,
        "topK": int(cfg["labeling"]["topK"]),
        "confidenceThreshold": float(cfg["labeling"]["confidenceThreshold"]),
        "marginThreshold": float(cfg["labeling"]["marginThreshold"]),
        "pathLegalRate": (
            round(1 - invalid_label_count / max(1, labeled_total), 6)
        ),
        "unclassifiedByReason": dict(sorted(Counter(
            entry["reasonCode"] for entry in unclassified
        ).items())),
        "toolErrors": dict(sorted(tool_errors.items())),
        "evidenceSources": {
            "text": int(modality_counts.get("text", 0)),
            "ocrImages": int(modality_counts.get("image", 0)),
            "asrAudios": int(modality_counts.get("audio", 0)),
            "videoFusion": int(modality_counts.get("video", 0)),
        },
        "toolVersions": {
            "rapidocr": _version("rapidocr-onnxruntime"),
            "funasr": _version("funasr"),
            "transformers": _version("transformers"),
        },
        "annotation": {
            "accuracy": None,
            "wilsonLower": None,
            "wilsonUpper": None,
            "confusionMatrix": None,
            "samplesPerModal": {},
            "blockedReason": "MATCHING_ANNOTATION_REQUIRED",
            "note": "无人工标注（H-05）；不填准确率/区间/混淆矩阵。",
        },
        "provisional": True,
        "generatedAt": now_iso(),
    }
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
        "modelVersion": model.model_version,
        "treeVersion": label_tree.tree_version,
        "treeHash": label_tree.tree_hash,
        "treeSnapshotPath": label_tree.snapshot_path.as_posix(),
        "paramsHash": f"sha256:{params_hash(resolved_params)}",
        "seed": resolved_seed,
        "sampleCount": len(result_rows),
        "successCount": labeled_total,
        "failedCount": len(failures),
        "inputBytes": records_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / records_bytes, 6) if records_bytes else 0.0,
        "artifacts": payload_artifacts,
        "failedSamples": failures[:MAX_FAILURES],
        "createdAt": now_iso(),
        "notes": [
            "零样本打标：bge 标签向量 + 内容向量余弦相似度；非训练型分类器，需人工验证。",
            "图像/视频文字来自 RapidOCR，音频/视频语音来自 FunASR paraformer-zh。",
            "无人工标注时不填准确率；低置信/无证据样本进 unclassified.jsonl。",
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
        "treeVersion": manifest["treeVersion"],
        "treeHash": manifest["treeHash"],
        "sampleCount": len(result_rows),
        "successCount": labeled_total,
        "failedCount": len(failures),
        "metrics": metrics,
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(summary_path, summary)

    artifacts = _collect_artifacts(output, exclude={"result.json", "error.log"})
    return {
        "modelVersion": manifest["modelVersion"],
        "treeVersion": manifest["treeVersion"],
        "treeHash": manifest["treeHash"],
        "sampleCount": len(result_rows),
        "successCount": labeled_total,
        "failedCount": len(failures),
        "failedSamples": failures[:MAX_FAILURES],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "四模态证据来自真实 OCR/ASR/文本；无证据样本不伪造标签。",
            "零样本标签与阈值属联调方案，准确率需人工标注后评测。",
        ],
    }


def _label_record(
    record: dict[str, Any],
    records_root: Path,
    standard_paths: dict[str, str],
    derived_audio: dict[str, dict[str, Any]],
    model,
    label_matrix: np.ndarray,
    label_tree,
    cfg: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    modal = record["modal"]
    record_id = record["record_id"]
    max_chars = int(cfg["limits"]["maxTextChars"])
    min_chars = int(cfg["labeling"]["minEvidenceChars"])
    if modal == "text":
        text = (record.get("text") or "").strip()[:max_chars]
        if len(text) < min_chars:
            return _unclassified("UNCLASSIFIED_EMPTY_TEXT", {"source": "text", "chars": len(text)})
        return labeler.label_text(
            model, label_matrix, label_tree, text, cfg,
            evidence={"source": "text", "chars": len(text), "preview": text[:200]},
        )
    if modal == "image":
        path = _standard_path(record, records_root, standard_paths)
        if path is None:
            raise FileNotFoundError(f"标准图像不存在：{record_id}")
        result = ocr.ocr_image(path)
        text = result["text"][:max_chars]
        if len(text) < min_chars:
            return _unclassified(
                "UNCLASSIFIED_NO_TEXT_EVIDENCE",
                {"source": "ocr", "chars": len(text), "items": 0},
            )
        return labeler.label_text(
            model, label_matrix, label_tree, text, cfg,
            evidence={
                "source": "ocr",
                "chars": len(text),
                "preview": text[:200],
                "items": result["items"][:10],
                "standardPath": _relative(path, records_root),
            },
        )
    if modal == "audio":
        path = _standard_path(record, records_root, standard_paths)
        if path is None:
            raise FileNotFoundError(f"标准音频不存在：{record_id}")
        result = asr.transcribe(
            path, cfg, max_seconds=int(cfg["limits"]["maxAudioSec"])
        )
        text = result["text"][:max_chars]
        if len(text) < min_chars:
            return _unclassified(
                "UNCLASSIFIED_NO_SPEECH",
                {"source": "asr", "chars": len(text), "durationSec": result.get("durationSec")},
            )
        return labeler.label_text(
            model, label_matrix, label_tree, text, cfg,
            evidence={
                "source": "asr",
                "chars": len(text),
                "preview": text[:500],
                "durationSec": result.get("durationSec"),
                "segments": result.get("segments"),
                "standardPath": _relative(path, records_root),
            },
        )
    if modal == "video":
        path = _standard_path(record, records_root, standard_paths)
        if path is None:
            raise FileNotFoundError(f"标准视频不存在：{record_id}")
        duration = (record.get("metadata") or {}).get("durationSec")
        frames = vision.extract_keyframes(
            path,
            output / "streams" / "keyframes" / record_id,
            max_frames=int(cfg["media"]["maxKeyframes"]),
            duration_sec=duration,
            timeout=int(cfg["limits"]["ffmpegTimeoutSec"]),
        )
        ocr_texts: list[str] = []
        ocr_items: list[dict[str, Any]] = []
        for frame in frames:
            try:
                result = ocr.ocr_image(frame["path"])
            except Exception:  # noqa: BLE001 - 单帧 OCR 失败继续
                continue
            if result["text"].strip():
                ocr_texts.append(result["text"])
                ocr_items.extend(
                    {**item, "tsSec": frame["tsSec"]} for item in result["items"][:5]
                )
        ocr_text = "\n".join(ocr_texts)[:max_chars]

        asr_text = ""
        audio_record = derived_audio.get(record_id)
        audio_evidence = None
        if audio_record is not None and cfg["media"].get("asrEnabled", True):
            audio_path = _standard_path(audio_record, records_root, standard_paths)
            if audio_path is not None:
                audio_result = asr.transcribe(
                    audio_path, cfg, max_seconds=int(cfg["limits"]["maxAudioSec"])
                )
                asr_text = audio_result["text"][:max_chars]
                audio_evidence = {
                    "chars": len(asr_text),
                    "preview": asr_text[:500],
                    "durationSec": audio_result.get("durationSec"),
                }

        vectors: list[np.ndarray] = []
        weights: list[float] = []
        fusion = cfg["media"]["videoFusion"]
        if len(ocr_text) >= min_chars:
            vectors.append(model.encode_document(ocr_text))
            weights.append(float(fusion["ocr"]))
        if len(asr_text) >= min_chars:
            vectors.append(model.encode_document(asr_text))
            weights.append(float(fusion["asr"]))
        evidence = {
            "source": "video_fusion",
            "ocr": {
                "chars": len(ocr_text),
                "preview": ocr_text[:200],
                "keyframes": [
                    {"index": frame["index"], "tsSec": frame["tsSec"],
                     "path": _relative(frame["path"], output)}
                    for frame in frames
                ],
                "items": ocr_items[:10],
            },
            "asr": audio_evidence,
            "chars": len(ocr_text) + len(asr_text),
        }
        if not vectors:
            return _unclassified("UNCLASSIFIED_NO_TEXT_EVIDENCE", evidence)
        fused = labeler.fuse_vectors(vectors, weights)
        return labeler.label_vector(
            model, label_matrix, label_tree, fused, cfg, evidence=evidence
        )
    return _unclassified(
        "UNSUPPORTED_MODAL", {"source": modal, "chars": 0}
    )


def _unclassified(reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "labels": [],
        "topK": [],
        "unclassified": True,
        "reasonCode": reason,
        "top1": None,
        "margin": None,
        "evidence": evidence,
    }


def _standard_path(
    record: dict[str, Any], records_root: Path, standard_paths: dict[str, str]
) -> Path | None:
    record_id = record["record_id"]
    relative = standard_paths.get(record_id)
    if relative:
        candidate = records_root / relative
        if candidate.is_file():
            return candidate
    modal = record["modal"]
    if modal == "image":
        candidate = records_root / "standard" / "images" / f"{record_id}.webp"
    elif modal == "audio":
        candidate = records_root / "standard" / "audio" / f"{record_id}.wav"
    else:
        candidate = records_root / "standard" / "video" / f"{record_id}.mp4"
    if candidate.is_file():
        return candidate
    if modal == "video":
        matches = sorted((records_root / "standard" / "video").glob(f"{record_id}.*"))
        if matches:
            return matches[0]
    return None


def _index_standard_paths(records_root: Path) -> dict[str, str]:
    path = records_root / "index" / "metadata.parquet"
    if not path.is_file():
        return {}
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(path, columns=["record_id", "standard_path"])
        return {
            str(row["record_id"]): str(row["standard_path"])
            for row in table.to_pylist()
            if row.get("standard_path")
        }
    except Exception:  # noqa: BLE001 - 索引缺失时回退约定路径
        return {}


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _apply_overrides(cfg: dict[str, Any], params: dict[str, Any]) -> None:
    if "top_k" in params:
        cfg["labeling"]["topK"] = max(1, min(20, int(params["top_k"])))
    if "confidence_threshold" in params:
        cfg["labeling"]["confidenceThreshold"] = float(params["confidence_threshold"])
    if "margin_threshold" in params:
        cfg["labeling"]["marginThreshold"] = float(params["margin_threshold"])
    if "max_records" in params:
        cfg["limits"]["maxRecords"] = max(1, int(params["max_records"]))
    if "ocr_enabled" in params:
        cfg["media"]["ocrEnabled"] = bool(params["ocr_enabled"])
    if "asr_enabled" in params:
        cfg["media"]["asrEnabled"] = bool(params["asr_enabled"])
    if "device" in params:
        cfg["model"]["device"] = str(params["device"])


def _locate_records(input_path: str) -> tuple[Path, Path]:
    root = Path(input_path).resolve()
    if root.is_file():
        if root.suffix.lower() != ".jsonl":
            raise ValueError(f"只接受 .jsonl 记录文件，实际 {root.name}")
        return root, root.parent
    candidates = [
        root / "records.jsonl",
        root / "result.jsonl",
        root / "output" / "records.jsonl",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate, candidate.parent
    matches = sorted(root.glob("*.jsonl"))
    if matches:
        return matches[0], matches[0].parent
    raise FileNotFoundError(f"目录中没有 records.jsonl：{root}")


def _iter_records(path: Path, max_records: int):
    with path.open("r", encoding="utf-8") as source:
        for number, line in enumerate(source, start=1):
            if number > max_records:
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                yield number, None, f"JSON_PARSE_FAILED: {exc.msg}"
                continue
            if not isinstance(payload, dict):
                yield number, None, "RECORD_NOT_OBJECT"
                continue
            yield number, payload, None


def _relative(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _collect_artifacts(output: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    from .utils.common import file_hashes

    artifacts: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*"), key=lambda item: item.relative_to(output).as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in exclude:
            continue
        suffix = path.suffix.lower()
        artifacts.append(
            {
                "type": {
                    ".jsonl": "jsonl",
                    ".json": "json",
                    ".npy": "vectors",
                    ".jpg": "keyframe",
                }.get(suffix, "file"),
                "path": path.as_posix(),
                "sha256": file_hashes(path)[1],
                "bytes": path.stat().st_size,
            }
        )
    return artifacts


def _clean_output(output: Path) -> None:
    for name in (
        "result.jsonl",
        "unclassified.jsonl",
        "failures.jsonl",
        "label_vectors.npy",
        "label_ids.jsonl",
        "input_manifest.json",
        "metrics.json",
        "manifest.json",
        "summary.json",
    ):
        (output / name).unlink(missing_ok=True)
    for name in ("streams",):
        shutil.rmtree(output / name, ignore_errors=True)


def _run_id(fingerprint: str, params: dict[str, Any], seed: int) -> str:
    return hashlib.sha256(
        f"{fingerprint}|{OPERATOR_VERSION}|{params_hash(params)}|{seed}".encode("utf-8")
    ).hexdigest()[:16]
