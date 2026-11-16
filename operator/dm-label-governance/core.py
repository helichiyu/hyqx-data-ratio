"""OP-07 标签治理（``corpus_label_governance_v1``）。

纯规则：树快照校验、非法路径最近节点建议、重复/跨领域冲突、低置信、PII 提示、
未归类原因汇总。治理建议只给建议，不自动改标签；无人工审核记录时质量指标为 null。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .utils import rules
from .utils.common import (
    ensure_output_dir,
    fingerprint_file,
    load_config,
    now_iso,
    params_hash,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-label-governance"
SEMANTIC_CODE = "corpus_label_governance_v1"
OPERATOR_VERSION = "0.1.0"
DEFAULT_SEED = 42


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

    input_file, input_root = _locate_input(input_path)
    trees = rules.Trees(cfg)

    result_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    illegal_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    pii_rows: list[dict[str, Any]] = []
    unclassified_rows: list[dict[str, Any]] = []
    attempted = 0
    label_total = 0
    illegal_total = 0
    suggestion_counts: Counter[str] = Counter()
    unclassified_counts: Counter[str] = Counter()

    for number, row, error in _iter_rows(input_file):
        attempted += 1
        if error:
            failures.append({"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": error})
            result_rows.append(
                {
                    "record_id": f"line:{number}",
                    "labels": [],
                    "legal": False,
                    "issues": [],
                    "reasonCode": "RECORD_JSON_INVALID",
                }
            )
            continue
        assert row is not None
        record_id = str(row.get("record_id") or f"line:{number}")
        labels = rules.extract_labels(row)
        label_total += len(labels)
        issues: list[dict[str, Any]] = []
        for label in labels:
            for issue in rules.label_issue(label, trees, cfg):
                issue["label"] = {
                    "path": label["path"],
                    "confidence": label.get("confidence"),
                    "sourceKey": label.get("sourceKey"),
                }
                issues.append(issue)
                suggestion_counts[issue["type"]] += 1
                if issue["type"] == "ILLEGAL_PATH":
                    illegal_total += 1
                    illegal_rows.append({"recordId": record_id, **issue})
        conflicts = rules.detect_conflicts(record_id, labels, cfg)
        conflict_rows.extend(conflicts)
        pii_text = _pii_text(row)
        pii_hits = rules.pii_scan(pii_text, cfg)
        if pii_hits:
            pii_rows.append({"recordId": record_id, "hits": pii_hits})
        unclassified = bool(row.get("unclassified")) or (not labels and row.get("reasonCode"))
        if unclassified:
            reason = row.get("reasonCode") or "UNCLASSIFIED"
            unclassified_counts[reason] += 1
            unclassified_rows.append(
                {"recordId": record_id, "reasonCode": reason, "topK": row.get("topK")}
            )
        legal = not any(issue["type"] == "ILLEGAL_PATH" for issue in issues) and not conflicts
        result_rows.append(
            {
                "record_id": record_id,
                "labels": labels,
                "legal": legal,
                "issues": issues[: int(cfg["rules"]["maxSuggestionsPerRecord"])],
                "conflicts": conflicts,
                "pii": pii_hits,
                "unclassified": unclassified,
                "reasonCode": row.get("reasonCode"),
            }
        )
        if not legal:
            failures.append(
                {
                    "id": record_id,
                    "reasonCode": "ILLEGAL_OR_CONFLICT",
                    "detail": f"非法标签 {sum(1 for item in issues if item['type']=='ILLEGAL_PATH')} 个，冲突 {len(conflicts)} 对",
                }
            )

    result_path = output / "result.jsonl"
    illegal_path = output / "illegal.jsonl"
    conflicts_path = output / "conflicts.jsonl"
    pii_path = output / "pii.jsonl"
    unclassified_path = output / "unclassified.jsonl"
    failures_path = output / "failures.jsonl"
    report_path = output / "governance_report.json"
    input_manifest_path = output / "input_manifest.json"
    metrics_path = output / "metrics.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"

    write_jsonl(result_path, result_rows)
    write_jsonl(illegal_path, illegal_rows)
    write_jsonl(conflicts_path, conflict_rows)
    write_jsonl(pii_path, pii_rows)
    write_jsonl(unclassified_path, unclassified_rows)
    write_jsonl(failures_path, failures)

    suggestions = [
        {
            "type": "ILLEGAL_PATH",
            "count": suggestion_counts.get("ILLEGAL_PATH", 0),
            "advice": "按 nearest 建议修正路径或回退到人工审核；不自动改写。",
        },
        {
            "type": "CROSS_DOMAIN_CONFLICT",
            "count": sum(1 for item in conflict_rows if item["type"] == "CROSS_DOMAIN_CONFLICT"),
            "advice": "核对是否跨领域多标签；若业务不允许，保留置信度更高者并记录理由。",
        },
        {
            "type": "LOW_CONFIDENCE",
            "count": suggestion_counts.get("LOW_CONFIDENCE", 0),
            "advice": "进入人工复核队列；阈值调整需版本化。",
        },
        {
            "type": "PII",
            "count": sum(len(item["hits"]) for item in pii_rows),
            "advice": "按平台隐私策略脱敏或移除；算子只提示不修改。",
        },
        {
            "type": "UNCLASSIFIED",
            "count": len(unclassified_rows),
            "advice": "分析未归类原因（无文字/低相似度/小边际），决定补数据或调阈值。",
        },
    ]
    report = {
        "treeVersion": trees.tree_version,
        "records": len(result_rows),
        "labels": label_total,
        "legalLabels": label_total - illegal_total,
        "illegalLabels": illegal_total,
        "legalRate": round((label_total - illegal_total) / max(1, label_total), 6),
        "conflicts": len(conflict_rows),
        "piiRecords": len(pii_rows),
        "unclassifiedRecords": len(unclassified_rows),
        "unclassifiedByReason": dict(sorted(unclassified_counts.items())),
        "suggestions": suggestions,
        "reviewMetrics": {
            "kappa": None,
            "alpha": None,
            "accuracy": None,
            "adoptionRate": None,
            "modificationRate": None,
            "blockedReason": "REVIEW_RECORDS_REQUIRED",
            "note": "无人工审核记录（H-05）；不填 Kappa/准确率/采纳率。",
        },
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(report_path, report)

    fingerprint, input_bytes = fingerprint_file(input_file)
    write_json(
        input_manifest_path,
        {
            "inputPath": input_file.as_posix(),
            "inputRoot": input_root.as_posix(),
            "inputFingerprint": f"sha256:{fingerprint}",
            "inputBytes": input_bytes,
            "note": "治理只读标签结果与树快照，不修改上游产物。",
        },
    )

    legal_records = sum(1 for row in result_rows if row.get("legal"))
    metrics = {
        "treeVersion": trees.tree_version,
        "records": len(result_rows),
        "labels": label_total,
        "illegalLabels": illegal_total,
        "legalRate": report["legalRate"],
        "conflicts": len(conflict_rows),
        "piiRecords": len(pii_rows),
        "unclassifiedRecords": len(unclassified_rows),
        "unclassifiedByReason": report["unclassifiedByReason"],
        "suggestionsByType": dict(sorted(suggestion_counts.items())),
        "reviewMetrics": report["reviewMetrics"],
        "modelVersion": None,
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
        "modelVersion": None,
        "treeVersion": trees.tree_version,
        "paramsHash": f"sha256:{params_hash(resolved_params)}",
        "seed": resolved_seed,
        "sampleCount": attempted,
        "successCount": legal_records,
        "failedCount": len(failures),
        "inputBytes": input_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / input_bytes, 6) if input_bytes else 0.0,
        "artifacts": payload_artifacts,
        "failedSamples": failures[:500],
        "createdAt": now_iso(),
        "notes": [
            "纯规则治理：无模型、无自动改标；建议以 nearest/置信度/冲突为依据。",
            "无人工审核记录时 Kappa/准确率/采纳率写 null + blockedReason。",
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
        "treeVersion": trees.tree_version,
        "sampleCount": attempted,
        "successCount": legal_records,
        "failedCount": len(failures),
        "metrics": metrics,
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(summary_path, summary)

    artifacts = _collect_artifacts(output, exclude={"result.json", "error.log"})
    return {
        "modelVersion": None,
        "treeVersion": trees.tree_version,
        "sampleCount": attempted,
        "successCount": legal_records,
        "failedCount": len(failures),
        "failedSamples": failures[:500],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "治理建议只读不写；是否入库由平台决定。",
            "无审核记录时质量指标为 null，不编造 Kappa/准确率。",
        ],
    }


def _pii_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    if isinstance(row.get("text"), str):
        parts.append(row["text"])
    evidence = row.get("evidence") or {}
    if isinstance(evidence.get("preview"), str):
        parts.append(evidence["preview"])
    for key in ("ocr", "asr"):
        nested = evidence.get(key) or {}
        if isinstance(nested.get("preview"), str):
            parts.append(nested["preview"])
    return "\n".join(parts)


def _apply_overrides(cfg: dict[str, Any], params: dict[str, Any]) -> None:
    if "min_confidence" in params:
        cfg["rules"]["minConfidence"] = float(params["min_confidence"])
    if "max_records" in params:
        cfg["limits"]["maxRecords"] = max(1, int(params["max_records"]))
    if "pii_enabled" in params:
        cfg["pii"]["enabled"] = bool(params["pii_enabled"])


def _locate_input(input_path: str) -> tuple[Path, Path]:
    root = Path(input_path).resolve()
    if root.is_file():
        if root.suffix.lower() != ".jsonl":
            raise ValueError(f"只接受 .jsonl 标签结果，实际 {root.name}")
        return root, root.parent
    for candidate in (
        root / "result.jsonl",
        root / "labels.jsonl",
        root / "output" / "result.jsonl",
    ):
        if candidate.is_file():
            return candidate, candidate.parent
    matches = sorted(root.glob("*.jsonl"))
    if matches:
        return matches[0], matches[0].parent
    raise FileNotFoundError(f"目录中没有标签结果 result.jsonl：{root}")


def _iter_rows(path: Path):
    with path.open("r", encoding="utf-8") as source:
        for number, line in enumerate(source, start=1):
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


def _collect_artifacts(output: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    from .utils.common import file_hashes

    artifacts: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*"), key=lambda item: item.relative_to(output).as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in exclude:
            continue
        artifacts.append(
            {
                "type": {".jsonl": "jsonl", ".json": "json"}.get(path.suffix.lower(), "file"),
                "path": path.as_posix(),
                "sha256": file_hashes(path)[1],
                "bytes": path.stat().st_size,
            }
        )
    return artifacts


def _clean_output(output: Path) -> None:
    for name in (
        "result.jsonl", "illegal.jsonl", "conflicts.jsonl", "pii.jsonl",
        "unclassified.jsonl", "failures.jsonl", "governance_report.json",
        "input_manifest.json", "metrics.json", "manifest.json", "summary.json",
    ):
        (output / name).unlink(missing_ok=True)


def _run_id(fingerprint: str, params: dict[str, Any], seed: int) -> str:
    return hashlib.sha256(
        f"{fingerprint}|{OPERATOR_VERSION}|{params_hash(params)}|{seed}".encode("utf-8")
    ).hexdigest()[:16]
