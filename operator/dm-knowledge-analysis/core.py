"""OP-13 知识覆盖、热点与风格（``corpus_profile_knowledge_style_v1``）。

消费 OP-02 文本：术语表（可选）匹配的覆盖率与知识密度、事实/推理/创意占比、热点/长尾、
语体占比。无 KG/术语表时相关指标标 ``unavailable``，不编造。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from .utils import style as style_util
from .utils import terms as terms_util
from .utils import timewin
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

OPERATOR_ID = "dm-knowledge-analysis"
SEMANTIC_CODE = "corpus_profile_knowledge_style_v1"
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
    glossary_path = _locate(resolved.get("glossary_path"))
    glossary = terms_util.load_glossary(glossary_path, int(cfg["terms"]["maxTerms"]))
    automaton = terms_util.Automaton(list(glossary)) if glossary else None
    max_chars = int(cfg["limits"]["maxTextChars"])
    max_records = int(resolved.get("max_records", cfg["limits"]["maxRecords"]))

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    style_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    window_counts: Counter[str] = Counter()
    coverage_values: list[float] = []
    density_values: list[float] = []
    matched_terms: set[str] = set()
    years: list[int] = []
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
            text = (record.get("text") or "")[:max_chars]
            if not text.strip():
                failures.append({"id": record_id, "reasonCode": "EMPTY_TEXT"})
                continue
            term_report = terms_util.analyze(text, automaton, glossary)
            knowledge = style_util.classify_knowledge(text, cfg)
            style = style_util.classify_style(text, cfg)
            year = timewin.extract_year(
                (record.get("metadata") or {}).get("capturedAt"), text, cfg["hotspot"]["yearRegex"]
            )
            if term_report["status"] == "ok":
                coverage_values.append(term_report["coverage"])
                if term_report["densityPer100Chars"] is not None:
                    density_values.append(term_report["densityPer100Chars"])
                matched_terms.update(term_report["allMatched"])
            style_counts[style["style"]] += 1
            type_counts[knowledge["type"]] += 1
            if year is not None:
                years.append(year)
            term_report = {key: value for key, value in term_report.items() if key != "allMatched"}
            rows.append(
                {
                    "record_id": record_id,
                    "textChars": len(text),
                    "terms": term_report,
                    "knowledgeType": knowledge["type"],
                    "knowledgeShares": knowledge["shares"],
                    "style": style["style"],
                    "styleConfidence": style["confidence"],
                    "year": year,
                    "freshnessClass": None,
                }
            )

    as_of = _as_of(resolved, years)
    for row in rows:
        row["freshnessClass"] = timewin.classify(
            row["year"], as_of, int(cfg["hotspot"]["windowDays"])
        )
        window_counts[row["freshnessClass"]] += 1

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
            "glossaryPath": glossary_path.as_posix() if glossary_path else None,
            "glossaryTerms": len(glossary),
            "note": "术语匹配用 Aho–Corasick；无术语表/KG 时覆盖率标 unavailable。",
        },
    )

    total_style = sum(style_counts.values())
    total_type = sum(type_counts.values())
    metrics = {
        "textRecords": text_records,
        "skippedNonText": skipped_non_text,
        "evaluatedRecords": len(rows),
        "failedCount": len(failures),
        "failuresByReason": dict(sorted(Counter(item["reasonCode"] for item in failures).items())),
        "terms": {
            "status": "ok" if glossary else "unavailable",
            "reasonCode": None if glossary else "GLOSSARY_UNAVAILABLE",
            "glossaryTerms": len(glossary),
            "matchedTerms": len(matched_terms),
            "corpusCoverage": round(len(matched_terms) / len(glossary), 6) if glossary else None,
            "coverageMean": round(sum(coverage_values) / len(coverage_values), 6) if coverage_values else None,
            "densityMeanPer100Chars": round(sum(density_values) / len(density_values), 6) if density_values else None,
        },
        "entityCoverage": {
            "status": "unavailable",
            "reasonCode": "KG_UNAVAILABLE",
            "note": "未提供知识图谱/实体词表，不产出实体覆盖率。",
        },
        "knowledgeTypes": {
            "counts": dict(sorted(type_counts.items())),
            "shares": {name: round(count / total_type, 6) for name, count in type_counts.items()}
            if total_type
            else {},
            "method": "keyword-rule hit share",
        },
        "styles": {
            "counts": dict(sorted(style_counts.items())),
            "shares": {name: round(count / total_style, 6) for name, count in style_counts.items()}
            if total_style
            else {},
        },
        "hotspot": {
            "windowDays": cfg["hotspot"]["windowDays"],
            "counts": dict(sorted(window_counts.items())),
            "asOf": as_of.isoformat(),
        },
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
        "modelVersion": "rule-based-knowledge-v1",
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
            "术语覆盖率需要术语表；未提供时标 unavailable，不编造。",
            "实体覆盖率需要知识图谱，标 KG_UNAVAILABLE。",
            "事实/推理/创意与语体为关键词规则，占比可复算。",
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
            "无术语表时 terms.status=unavailable；无 KG 时 entityCoverage=unavailable。",
            "热点窗口 365 天可配置，长尾按批次最大年份计算。",
        ],
    }


def _as_of(params: dict[str, Any], years: list[int]) -> date:
    raw = params.get("as_of")
    if raw:
        return date.fromisoformat(str(raw)[:10])
    return date(max(years), 12, 31) if years else date.today()


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
