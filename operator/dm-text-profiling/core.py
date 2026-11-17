"""OP-10 文本属性与任务适配（``corpus_profile_text_taskfit_v1``）。

消费 OP-02 文本记录：句长/从句/被动/TTR/MSTTR/MTLD/语体 + 六维任务适配分。
可选消费 OP-06 领域标签作为 domainMatch 子指标；缺失时该组不参与并写 reasonCode。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .utils import genre as genre_util
from .utils import lexical, segment, syntax, taskfit
from .utils.common import (
    ensure_output_dir,
    ensure_under_roots,
    environment_roots,
    fingerprint_file,
    load_config,
    locate_records,
    now_iso,
    params_hash,
    percentile_nearest_rank,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-text-profiling"
SEMANTIC_CODE = "corpus_profile_text_taskfit_v1"
OPERATOR_VERSION = "0.1.0"
DEFAULT_SEED = 42
DIMENSIONS = [
    "sentenceCompleteness",
    "clauseComplexity",
    "lexicalRichness",
    "informationDensity",
    "domainMatch",
    "genreFit",
]


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
    domain_map = _load_domain_confidences(domain_labels)
    max_chars = int(cfg["segment"]["maxTextChars"])
    max_records = int(resolved.get("max_records", cfg["limits"]["maxRecords"]))

    rows: list[dict[str, Any]] = []
    low_fit: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    genre_counts: Counter[str] = Counter()
    value_lists: dict[str, list[float]] = {name: [] for name in DIMENSIONS}
    value_lists["overall"] = []
    attempted = 0
    text_records = 0
    skipped_non_text = 0

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
            if record.get("modal") != "text":
                skipped_non_text += 1
                continue
            text_records += 1
            record_id = str(record.get("record_id") or f"line:{number}")
            text = (record.get("text") or "").strip()
            if not text:
                failures.append({"id": record_id, "reasonCode": "EMPTY_TEXT"})
                rows.append(
                    {
                        "record_id": record_id,
                        "textChars": 0,
                        "sentenceCount": 0,
                        "tokenCount": 0,
                        "ttr": None,
                        "msttr": None,
                        "mtld": None,
                        "genre": None,
                        "genreConfidence": None,
                        "dimensions": {name: None for name in DIMENSIONS},
                        "groups": None,
                        "overall": None,
                        "lowFit": None,
                        "reasonCode": "EMPTY_TEXT",
                    }
                )
                continue
            text = text[:max_chars]
            tokens = segment.words(text, cfg)
            lex = lexical.summary(tokens, cfg)
            syn = syntax.analyze(text, cfg)
            gen = genre_util.classify(text, cfg)
            domain_confidence = domain_map.get(record_id)
            fit = taskfit.score(lex, syn, gen, domain_confidence, len(text), cfg)

            genre_counts[gen["genre"]] += 1
            for name in DIMENSIONS:
                value = fit["dimensions"][name]
                if value is not None:
                    value_lists[name].append(float(value))
            value_lists["overall"].append(float(fit["overall"]))

            row = {
                "record_id": record_id,
                "textChars": len(text),
                "sentenceCount": syn["sentenceCount"],
                "sentenceCharsMean": syn["sentenceCharsMean"],
                "clausesPerSentenceMean": syn["clausesPerSentenceMean"],
                "clauseDepthMean": syn["clauseDepthMean"],
                "passiveRate": syn["passiveRate"],
                "completeSentenceRate": syn["completeSentenceRate"],
                "punctuationPer100Chars": syn["punctuationPer100Chars"],
                "tokenCount": lex["tokenCount"],
                "uniqueTokens": lex["uniqueTokens"],
                "ttr": lex["ttr"],
                "msttr": lex["msttr"],
                "mtld": lex["mtld"],
                "meanTokenChars": lex["meanTokenChars"],
                "genre": gen["genre"],
                "genreConfidence": gen["confidence"],
                "dimensions": fit["dimensions"],
                "groups": fit["groups"],
                "overall": fit["overall"],
                "lowFit": fit["lowFit"],
                "reasonCode": fit["reasonCode"],
            }
            rows.append(row)
            if fit["lowFit"]:
                low_fit.append(
                    {
                        "record_id": record_id,
                        "overall": fit["overall"],
                        "dimensions": fit["dimensions"],
                        "genre": gen["genre"],
                    }
                )

    result_path = output / "result.jsonl"
    failures_path = output / "failures.jsonl"
    low_fit_path = output / "low_fit.jsonl"
    metrics_path = output / "metrics.json"
    input_manifest_path = output / "input_manifest.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, rows)
    write_jsonl(failures_path, failures)
    write_jsonl(low_fit_path, low_fit)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "domainLabelsPath": domain_labels.as_posix() if domain_labels else None,
            "domainLabelsMatched": len(domain_map),
            "note": "只消费 OP-02 文本记录；领域匹配只读 OP-06 结果文件。",
        },
    )

    percentiles = [50, 90, 99]
    metrics = {
        "textRecords": text_records,
        "skippedNonText": skipped_non_text,
        "evaluatedRecords": len(value_lists["overall"]),
        "failedCount": len(failures),
        "failuresByReason": dict(sorted(Counter(item["reasonCode"] for item in failures).items())),
        "genreCounts": dict(sorted(genre_counts.items(), key=lambda item: (-item[1], item[0]))),
        "distributions": {
            name: {
                f"p{int(p)}": percentile_nearest_rank(values, float(p)) for p in percentiles
            }
            for name, values in value_lists.items()
            if values
        },
        "lowFitCount": len(low_fit),
        "lowFitThreshold": cfg["taskfit"]["lowFitThreshold"],
        "weights": {
            "groupWeights": cfg["taskfit"]["groupWeights"],
            "subWeights": cfg["taskfit"]["subWeights"],
        },
        "domainMatchStatus": "ok" if domain_map else "unavailable",
        "domainMatchReasonCode": None if domain_map else "DOMAIN_LABELS_UNAVAILABLE",
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
        "modelVersion": "rule-based-text-metrics-v1",
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": text_records,
        "successCount": len(rows),
        "failedCount": len(failures),
        "inputBytes": records_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / records_bytes, 6) if records_bytes else 0.0,
        "artifacts": artifacts,
        "failedSamples": failures,
        "createdAt": now_iso(),
        "notes": [
            "无依存句法模型：从句数按标点分句，从句深度按从属连词近似，规则写入 configs/text.json。",
            "TTR 对长度敏感，同时输出 MSTTR(50) 与近似 MTLD(0.72)。",
            "domainMatch 依赖 OP-06；缺失时 domain 组不参与，权重重归一化并写 reasonCode。",
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
        "sampleCount": text_records,
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
        "sampleCount": text_records,
        "successCount": len(rows),
        "failedCount": len(failures),
        "failedSamples": failures,
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "六维 = 结构(完整性/复杂度) + 语义(丰富度/信息密度) + 领域(领域匹配/语体适配)。",
            "低适配清单为整体分 < 3.0 的记录，阈值可配置。",
        ],
    }


def _locate_domain_labels(params: dict[str, Any]) -> Path | None:
    raw = params.get("domain_labels_path")
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


def _load_domain_confidences(path: Path | None) -> dict[str, float]:
    if path is None or not path.is_file():
        return {}
    mapping: dict[str, float] = {}
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
            labels = row.get("domainLabels") or []
            confidences = [
                float(label["confidence"])
                for label in labels
                if isinstance(label, dict) and isinstance(label.get("confidence"), (int, float))
            ]
            if record_id and confidences:
                mapping[str(record_id)] = sum(confidences) / len(confidences)
    return mapping


def _clean_output(output: Path) -> None:
    for name in ("result.jsonl", "failures.jsonl", "low_fit.jsonl", "metrics.json", "manifest.json", "summary.json", "input_manifest.json"):
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
