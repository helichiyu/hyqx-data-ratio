"""OP-14 质量、一致性与难度（``corpus_profile_quality_difficulty_v1``）。

消费 OP-02 记录：完整率、跨文档冲突（SimHash）、基尼系数（OP-05 标签）、标注覆盖、
多模态一致性、难度四档与极性占比。无上游标签时不产出基尼/覆盖，标 unavailable。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .utils import completeness as completeness_util
from .utils import conflict as conflict_util
from .utils import difficulty as difficulty_util
from .utils import gini as gini_util
from .utils import labels as labels_util
from .utils import polarity as polarity_util
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

OPERATOR_ID = "dm-quality-analysis"
SEMANTIC_CODE = "corpus_profile_quality_difficulty_v1"
OPERATOR_VERSION = "0.1.0"
DEFAULT_SEED = 42
SENTENCE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;\n]?")
CLAUSE = re.compile(r"[^，,、；;：:]+")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*|[一-鿿]")


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
    labels_path = _locate_file(resolved.get("labels_path"))
    label_map = labels_util.load(labels_path)
    max_records = int(resolved.get("max_records", cfg["limits"]["maxRecords"]))

    raw_records: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    quality_values: list[float] = []
    missing_counter: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    polarity_counts: Counter[str] = Counter()
    token_counts: Counter[str] = Counter()
    per_record_tokens: dict[str, list[str]] = {}
    text_by_id: dict[str, str] = {}
    texts: list[tuple[str, str]] = []
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
            modal = record.get("modal")
            text = record.get("text") if isinstance(record.get("text"), str) else ""
            raw_records.append(
                {
                    "record_id": record_id,
                    "metadata": {"extra": (record.get("metadata") or {}).get("extra") or {}},
                }
            )
            text_by_id[record_id] = text
            completeness = completeness_util.evaluate(record, cfg)
            quality_values.append(completeness["rate"])
            missing_counter.update(completeness["missingFields"])
            tokens = WORD.findall(text.lower())
            token_counts.update(tokens)
            if tokens:
                per_record_tokens[record_id] = tokens
            if text.strip():
                texts.append((record_id, text))
            rows.append(
                {
                    "record_id": record_id,
                    "modal": modal,
                    "completeness": completeness["rate"],
                    "lowCompleteness": completeness["lowCompleteness"],
                    "missingFields": completeness["missingFields"],
                    "blankText": completeness["blankText"],
                    "labels": len(label_map.get(record_id) or []),
                    "polarity": None,
                    "polarityScore": None,
                    "difficulty": None,
                    "difficultyLevel": None,
                }
            )

    rarity_threshold = _median_frequency(token_counts)
    for row in rows:
        tokens = per_record_tokens.get(row["record_id"])
        if not tokens:
            continue
        sentences = [item for item in SENTENCE.findall(text_by_id.get(row["record_id"], "")) if item.strip()]
        sentence_chars = [len(item.strip()) for item in sentences]
        clauses = [
            max(1, len([part for part in CLAUSE.findall(item) if part.strip()]))
            for item in sentences
        ]
        rarity = (
            sum(1 for token in tokens if token_counts[token] <= rarity_threshold) / len(tokens)
            if tokens
            else 0.0
        )
        difficulty = difficulty_util.score(
            sum(sentence_chars) / len(sentence_chars) if sentence_chars else None,
            sum(clauses) / len(clauses) if clauses else None,
            rarity,
            cfg,
        )
        polarity = polarity_util.analyze(text_by_id.get(row["record_id"], ""), cfg)
        row["difficulty"] = difficulty["score"]
        row["difficultyLevel"] = difficulty["level"]
        row["polarity"] = polarity["polarity"]
        row["polarityScore"] = polarity["score"]
        difficulty_counts[difficulty["level"]] += 1
        polarity_counts[polarity["polarity"]] += 1

    conflict_report = conflict_util.analyze(texts, cfg)
    label_counts_all = labels_util.counts(label_map, level=2)
    label_counts_l1 = labels_util.counts(label_map, level=0)
    gini_report = gini_util.analyze(label_counts_all, cfg) if label_map else {
        "status": "unavailable",
        "reasonCode": "LABELS_UNAVAILABLE",
        "gini": None,
        "threshold": cfg["gini"]["threshold"],
    }
    coverage_report = labels_util.coverage(label_map, [row["record_id"] for row in rows])
    consistency_report = labels_util.multimodal_consistency(raw_records, label_map)

    total_polarity = sum(polarity_counts.values())
    balanced = _balance(polarity_counts, total_polarity)

    low_quality = [
        {
            "record_id": row["record_id"],
            "reasons": _quality_reasons(row),
        }
        for row in rows
        if _quality_reasons(row)
    ]

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
            "labelsPath": labels_path.as_posix() if labels_path else None,
            "labelsMatched": len(label_map),
            "note": "标签只读 OP-05 结果文件；冲突/难度/极性全部由记录文本计算。",
        },
    )

    metrics = {
        "records": len(rows),
        "completeness": {
            "mean": round(sum(quality_values) / len(quality_values), 6) if quality_values else None,
            "lowCompletenessCount": sum(1 for value in quality_values if value < float(cfg["completeness"]["lowCompleteness"])),
            "missingFieldCounts": dict(sorted(missing_counter.items(), key=lambda item: (-item[1], item[0]))),
            "blankTextCount": sum(1 for row in rows if row["blankText"]),
        },
        "conflict": conflict_report,
        "gini": gini_report,
        "annotation": {
            **coverage_report,
            "level1Distribution": dict(
                sorted(label_counts_l1.items(), key=lambda item: (-item[1], item[0]))
            ),
        },
        "multimodalConsistency": consistency_report,
        "difficulty": {
            "counts": dict(sorted(difficulty_counts.items())),
            "bands": cfg["difficulty"]["bands"],
            "weights": cfg["difficulty"]["weights"],
        },
        "polarity": {
            "counts": dict(sorted(polarity_counts.items())),
            "shares": {
                name: round(count / total_polarity, 6)
                for name, count in polarity_counts.items()
            }
            if total_polarity
            else {},
            "balance": balanced,
            "method": "lexicon + negation (rule-based)",
        },
        "lowQualityCount": len(low_quality),
        "failedCount": len(failures),
        "failuresByReason": dict(sorted(Counter(item["reasonCode"] for item in failures).items())),
        "treeVersion": None,
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
        "modelVersion": "rule-based-quality-v1",
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
            "冲突用 SimHash(64) 近重复组 + 组内文本不一致定义；规则写入 configs/quality.json。",
            "基尼/覆盖需要 OP-05 标签；缺失时 unavailable，不编造。",
            "难度为文本复杂度规则分档；极性为自建词典规则，非情感模型。",
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
            "完整率/冲突/基尼/难度/极性均可由 result.jsonl 与 metrics.json 复算。",
            "低质量清单列出完整率不足、空文本等记录，供 OP-15 过滤。",
        ],
    }


def _median_frequency(counter: Counter[str]) -> float:
    if not counter:
        return 0.0
    ordered = sorted(counter.values())
    return float(ordered[len(ordered) // 2])


def _balance(counts: Counter[str], total: int) -> float | None:
    if not total:
        return None
    positive = counts.get("positive", 0)
    negative = counts.get("negative", 0)
    extreme = abs(positive - negative)
    return round(1.0 - extreme / total, 6)


def _quality_reasons(row: dict[str, Any]) -> list[str]:
    reasons = []
    if row["lowCompleteness"]:
        reasons.append("LOW_COMPLETENESS")
    if row["blankText"]:
        reasons.append("EMPTY_TEXT")
    return reasons


def _locate_file(raw: Any) -> Path | None:
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
