"""OP-12 图像/视频属性（``corpus_profile_visual_attributes_v1``）。

消费 OP-02 标准图像（WebP）与视频（MP4）：图像熵/清晰度/亮度/色彩/主色；视频镜头切换、
平均镜头时长、光流动态/静态占比、关键帧时间。场景/目标/动作与音画 BLEU 无模型/参考时
标 ``unavailable``，不编造。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .utils import image as image_util
from .utils import video as video_util
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

OPERATOR_ID = "dm-visual-analysis"
SEMANTIC_CODE = "corpus_profile_visual_attributes_v1"
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
    media_counts: Counter[str] = Counter()
    entropy_values: list[float] = []
    sharpness_values: list[float] = []
    dynamic_values: list[float] = []
    shot_values: list[float] = []
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
            modal = record.get("modal")
            if modal not in {"image", "video"}:
                continue
            media_counts[modal] += 1
            record_id = str(record.get("record_id") or f"line:{number}")
            if modal == "image":
                path = records_root / cfg["media"]["imageDir"] / f"{record_id}{cfg['media']['imageExt']}"
                analyzer = image_util.analyze
            else:
                path = records_root / cfg["media"]["videoDir"] / f"{record_id}{cfg['media']['videoExt']}"
                analyzer = video_util.analyze
            if not path.is_file():
                failures.append({"id": record_id, "reasonCode": "STANDARD_MEDIA_MISSING"})
                continue
            try:
                stats = analyzer(path, cfg)
            except Exception as exc:  # noqa: BLE001 - 解码失败记录原因
                failures.append({"id": record_id, "reasonCode": "DECODE_FAILED", "detail": str(exc)})
                continue
            row = {"record_id": record_id, "modal": modal, **stats}
            rows.append(row)
            if modal == "image":
                entropy_values.append(stats["entropy"])
                sharpness_values.append(stats["sharpnessLaplacian"])
            else:
                if stats["dynamicFrameRatio"] is not None:
                    dynamic_values.append(stats["dynamicFrameRatio"])
                if stats["meanShotDurationSec"] is not None:
                    shot_values.append(stats["meanShotDurationSec"])

    result_path = output / "result.jsonl"
    failures_path = output / "failures.jsonl"
    metrics_path = output / "metrics.json"
    input_manifest_path = output / "input_manifest.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, rows)
    write_jsonl(failures_path, failures)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "note": "只处理 OP-02 标准图像/视频；场景/目标/动作模型缺失时标 unavailable。",
        },
    )

    metrics = {
        "mediaCounts": dict(sorted(media_counts.items())),
        "processedRecords": len(rows),
        "failedCount": len(failures),
        "failuresByReason": dict(sorted(Counter(item["reasonCode"] for item in failures).items())),
        "image": {
            "count": len(entropy_values),
            "entropyMean": round(sum(entropy_values) / len(entropy_values), 6) if entropy_values else None,
            "sharpnessMean": round(sum(sharpness_values) / len(sharpness_values), 6) if sharpness_values else None,
        },
        "video": {
            "count": len(dynamic_values),
            "dynamicFrameRatioMean": round(sum(dynamic_values) / len(dynamic_values), 6) if dynamic_values else None,
            "meanShotDurationSecMean": round(sum(shot_values) / len(shot_values), 6) if shot_values else None,
        },
        "unavailable": {
            "scene": cfg["unavailable"]["scene"],
            "object": cfg["unavailable"]["object"],
            "action": cfg["unavailable"]["action"],
            "audioVisualBleu": cfg["unavailable"]["audioVisualBleu"],
        },
        "modelVersion": "opencv-heuristics-v1",
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
        "modelVersion": "opencv-heuristics-v1",
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": sum(media_counts.values()),
        "successCount": len(rows),
        "failedCount": len(failures),
        "inputBytes": records_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / records_bytes, 6) if records_bytes else 0.0,
        "artifacts": artifacts,
        "failedSamples": failures,
        "createdAt": now_iso(),
        "notes": [
            "图像熵/清晰度/色彩与视频镜头/光流全部来自 OpenCV 真实计算。",
            "场景/目标/动作需要 CLIP/YOLO 权重（未审批），标 unavailable。",
            "音画 BLEU 需要字幕/ASR 参考，未提供时标 unavailable。",
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
        "sampleCount": sum(media_counts.values()),
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
        "sampleCount": sum(media_counts.values()),
        "successCount": len(rows),
        "failedCount": len(failures),
        "failedSamples": failures,
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "镜头边界为 HSV 直方图相关阈值；光流用 Farneback 平均幅值。",
            "场景/目标/动作与音画 BLEU 无模型/参考时标 unavailable。",
        ],
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
