"""OP-11 语音质量与声学属性（``corpus_profile_speech_quality_v1``）。

消费 OP-02 音频记录与标准 WAV：FunASR 转写、能量 VAD、语速、停顿、基频；有参考文本时
计算 WER/CER，无参考只给转写与声学统计，不冒充识别错误率。口音无模型，标 unavailable。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .utils import acoustic, asr, wer
from .utils.common import (
    DependencyUnavailable,
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

OPERATOR_ID = "dm-speech-analysis"
SEMANTIC_CODE = "corpus_profile_speech_quality_v1"
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
    references = _load_references(_locate(resolved.get("reference_path")))
    max_records = int(resolved.get("max_records", cfg["limits"]["maxRecords"]))

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    low_quality: list[dict[str, Any]] = []
    audio_records = 0
    attempted = 0
    reason_counter: Counter[str] = Counter()
    wer_values: list[float] = []
    cer_values: list[float] = []
    speech_ratios: list[float] = []
    pitch_values: list[float] = []

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
            if record.get("modal") != "audio":
                continue
            audio_records += 1
            record_id = str(record.get("record_id") or f"line:{number}")
            media = records_root / cfg["media"]["standardDir"] / f"{record_id}.wav"
            if not media.is_file():
                failures.append({"id": record_id, "reasonCode": "STANDARD_MEDIA_MISSING"})
                continue
            try:
                transcription = asr.transcribe(media, cfg)
            except (asr.AsrFailed, DependencyUnavailable) as exc:
                failures.append({"id": record_id, "reasonCode": "ASR_FAILED", "detail": str(exc)})
                continue
            text = str(transcription.get("text") or "")
            try:
                stats = acoustic.analyze(media, cfg, len(text))
            except Exception as exc:  # noqa: BLE001 - 解码失败记录原因
                failures.append({"id": record_id, "reasonCode": "DECODE_FAILED", "detail": str(exc)})
                continue

            reference = references.get(record_id)
            error = wer.measure(text, reference)
            reasons: list[str] = []
            if not text.strip():
                reasons.append("ASR_EMPTY")
            if stats["speechRatio"] is not None and stats["speechRatio"] < float(cfg["vad"]["minSpeechRatio"]):
                reasons.append("NO_SPEECH")
            if error["wer"] is not None and error["wer"] > float(cfg["quality"]["werLowQuality"]):
                reasons.append("WER_OVER_THRESHOLD")
            if error["cer"] is not None and error["cer"] > float(cfg["quality"]["cerLowQuality"]):
                reasons.append("CER_OVER_THRESHOLD")
            if error["wer"] is not None:
                wer_values.append(error["wer"])
            if error["cer"] is not None:
                cer_values.append(error["cer"])
            if stats["speechRatio"] is not None:
                speech_ratios.append(stats["speechRatio"])
            if stats["pitchMeanHz"] is not None:
                pitch_values.append(stats["pitchMeanHz"])

            row = {
                "record_id": record_id,
                "transcription": text,
                "chars": len(text),
                "asrSegments": transcription.get("segments"),
                "durationSec": stats["durationSec"],
                "speechRatio": stats["speechRatio"],
                "silenceRatio": stats["silenceRatio"],
                "speechSec": stats["speechSec"],
                "pauses": stats["pauses"],
                "pauseSec": stats["pauseSec"],
                "speechRateCharsPerSec": stats["speechRateCharsPerSec"],
                "pitchMeanHz": stats["pitchMeanHz"],
                "pitchMedianHz": stats["pitchMedianHz"],
                "voicedRatio": stats["voicedRatio"],
                "accent": stats["accent"],
                "wer": error["wer"],
                "cer": error["cer"],
                "werReasonCode": error["reasonCode"],
                "lowQuality": bool(reasons),
            }
            rows.append(row)
            if reasons:
                low_quality.append({"record_id": record_id, "reasons": reasons})
                reason_counter.update(reasons)

    result_path = output / "result.jsonl"
    failures_path = output / "failures.jsonl"
    low_quality_path = output / "low_quality.jsonl"
    metrics_path = output / "metrics.json"
    input_manifest_path = output / "input_manifest.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, rows)
    write_jsonl(failures_path, failures)
    write_jsonl(low_quality_path, low_quality)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "referencePath": references and "provided" or None,
            "referenceRecords": len(references),
            "note": "只处理 OP-02 音频记录的标准 WAV；无参考文本不计算 WER/CER。",
        },
    )

    metrics = {
        "audioRecords": audio_records,
        "processedRecords": len(rows),
        "failedCount": len(failures),
        "failuresByReason": dict(sorted(Counter(item["reasonCode"] for item in failures).items())),
        "transcribedRecords": sum(1 for row in rows if row["chars"] > 0),
        "speechRatioMean": round(sum(speech_ratios) / len(speech_ratios), 6) if speech_ratios else None,
        "pitchMeanHz": round(sum(pitch_values) / len(pitch_values), 6) if pitch_values else None,
        "werMean": round(sum(wer_values) / len(wer_values), 6) if wer_values else None,
        "cerMean": round(sum(cer_values) / len(cer_values), 6) if cer_values else None,
        "werStatus": "ok" if reference_available(references) else "unavailable",
        "werReasonCode": None if reference_available(references) else "REFERENCE_TEXT_REQUIRED",
        "lowQualityCount": len(low_quality),
        "lowQualityReasons": dict(sorted(reason_counter.items())),
        "thresholds": {
            "werLowQuality": cfg["quality"]["werLowQuality"],
            "cerLowQuality": cfg["quality"]["cerLowQuality"],
            "minSpeechRatio": cfg["vad"]["minSpeechRatio"],
        },
        "accent": {"status": "unavailable", "reasonCode": "ACCENT_MODEL_UNAVAILABLE"},
        "modelVersion": "paraformer-zh",
        "provisional": True,
        "deterministic": False,
        "deterministicNote": "ASR 为神经模型推理，CPU 上结果稳定但不同硬件可能有细微差异。",
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
        "modelVersion": "paraformer-zh",
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": audio_records,
        "successCount": len(rows),
        "failedCount": len(failures),
        "inputBytes": records_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / records_bytes, 6) if records_bytes else 0.0,
        "artifacts": artifacts,
        "failedSamples": failures,
        "createdAt": now_iso(),
        "notes": [
            "转写使用 paraformer-zh（Apache-2.0），CPU 推理，运行期不联网。",
            "WER/CER 只在提供参考文本时计算；无参考时 wer=null + REFERENCE_TEXT_REQUIRED。",
            "口音分类无模型，标 unavailable。",
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
        "sampleCount": audio_records,
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
        "sampleCount": audio_records,
        "successCount": len(rows),
        "failedCount": len(failures),
        "failedSamples": failures,
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": False,
        "provisional": True,
        "notes": [
            "WER/CER 需参考文本；无参考只产出转写与声学统计。",
            "低质量规则：无语音、ASR 空、WER>0.2、CER>0.3。",
        ],
    }


def reference_available(references: dict[str, str]) -> bool:
    return bool(references)


def _load_references(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            record_id = row.get("record_id")
            text = row.get("text")
            if record_id and isinstance(text, str):
                mapping[str(record_id)] = text
    return mapping


def _locate(raw: Any) -> Path | None:
    if not raw:
        return None
    try:
        target = ensure_under_roots(str(raw), environment_roots())
    except ValueError:
        return None
    if target.is_dir():
        matches = sorted(target.glob("*.jsonl"))
        return matches[0] if matches else None
    return target if target.is_file() else None


def _clean_output(output: Path) -> None:
    for name in ("result.jsonl", "failures.jsonl", "low_quality.jsonl", "metrics.json", "manifest.json", "summary.json", "input_manifest.json"):
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
