"""OP-06 领域/能力多标签（``corpus_label_taxonomy_multilabel_v1``）。

两个标签空间严格分离：领域树（16 行业）与能力树（8 大类）各自向量化、各自阈值裁剪，
不做跨空间合并。零样本方法与 OP-05 一致；无文字证据/低于阈值输出「未明确」。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .utils import embedder, tree
from .utils.common import (
    ensure_output_dir,
    fingerprint_file,
    load_config,
    now_iso,
    params_hash,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-taxonomy-labeling"
SEMANTIC_CODE = "corpus_label_taxonomy_multilabel_v1"
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

    records_path, records_root = _locate_records(input_path)
    model = embedder.Embedder(cfg)
    snapshot_override = str(resolved_params.get("tree_snapshot_path") or "").strip() or None
    expected_version = str(resolved_params.get("tree_version") or "").strip() or None
    trees: dict[str, tree.LabelTree] = {}
    matrices: dict[str, np.ndarray] = {}
    for space in cfg["tree"]["spaces"]:
        space_tree = tree.LabelTree(
            cfg["tree"]["relativePath"],
            space,
            override_path=snapshot_override,
            expected_version=expected_version,
        )
        trees[space] = space_tree
        matrices[space] = model.encode(space_tree.label_texts).astype(np.float32)
        np.save(output / f"label_vectors_{space}.npy", matrices[space].astype(np.float16))
        write_jsonl(
            output / f"label_ids_{space}.jsonl",
            [{"row": index, **item} for index, item in enumerate(space_tree.labels)],
        )

    result_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    skipped_non_text = 0
    attempted = 0
    labeled_counts = {space: 0 for space in trees}
    unknown_counts = {space: 0 for space in trees}
    label_counts: dict[str, list[int]] = {space: [] for space in trees}
    confidence_sum: defaultdict[str, float] = defaultdict(float)
    invalid_labels = 0

    for number, record, error in _iter_records(records_path, int(cfg["limits"]["maxRecords"])):
        if error:
            attempted += 1
            failures.append({"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": error})
            result_rows.append(
                {
                    "record_id": f"line:{number}",
                    "domainLabels": [],
                    "abilityLabels": [],
                    "unclassified": True,
                    "reasonCode": "RECORD_JSON_INVALID",
                }
            )
            continue
        assert record is not None
        if record.get("modal") != "text":
            skipped_non_text += 1
            continue
        attempted += 1
        record_id = str(record.get("record_id"))
        text = (record.get("text") or "").strip()[: int(cfg["limits"]["maxTextChars"])]
        if not text:
            unknown_counts = {space: unknown_counts[space] + 1 for space in trees}
            failures.append(
                {"id": record_id, "reasonCode": "UNCLASSIFIED_EMPTY_TEXT", "detail": "文本为空"}
            )
            result_rows.append(
                {
                    "record_id": record_id,
                    "domainLabels": [],
                    "abilityLabels": [],
                    "domainUnknown": True,
                    "abilityUnknown": True,
                    "unclassified": True,
                    "reasonCode": "UNCLASSIFIED_EMPTY_TEXT",
                }
            )
            continue
        vector = model.encode_document(text)
        evidence = {"source": "text", "chars": len(text), "preview": text[:200]}
        row: dict[str, Any] = {"record_id": record_id, "evidence": evidence}
        tops: dict[str, list[dict[str, Any]]] = {}
        any_label = False
        for space, space_tree in trees.items():
            labels, top = _labels_for_space(
                vector, matrices[space], space_tree, model, cfg, evidence
            )
            tops[space] = top
            key = f"{space}Labels"
            row[key] = labels
            row[f"{space}Unknown"] = not labels
            if labels:
                any_label = True
                labeled_counts[space] += 1
                label_counts[space].append(len(labels))
                confidence_sum[space] += float(labels[0]["confidence"])
                for label in labels:
                    if not space_tree.is_valid(label["path"]):
                        invalid_labels += 1
            else:
                unknown_counts[space] += 1
        row["topK"] = tops
        row["unclassified"] = not any_label
        row["reasonCode"] = None if any_label else "UNCLASSIFIED_LOW_SIMILARITY"
        result_rows.append(row)
        if not any_label:
            failures.append(
                {
                    "id": record_id,
                    "reasonCode": "UNCLASSIFIED_LOW_SIMILARITY",
                    "detail": "领域/能力两个空间均未达到阈值，输出「未明确」",
                }
            )

    result_path = output / "result.jsonl"
    failures_path = output / "failures.jsonl"
    input_manifest_path = output / "input_manifest.json"
    metrics_path = output / "metrics.json"
    manifest_path = output / "manifest.json"
    summary_path = output / "summary.json"
    write_jsonl(result_path, result_rows)
    write_jsonl(failures_path, failures)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "note": "只消费文本记录；非文本记录跳过并计数。",
        },
    )

    total_labels = sum(
        sum(len(row.get(f"{space}Labels") or []) for row in result_rows)
        for space in trees
    )
    metrics = {
        "treeVersion": next(iter(trees.values())).tree_version if trees else None,
        "treeHash": next(iter(trees.values())).tree_hash if trees else None,
        "labelSpaceSizes": {space: len(item.labels) for space, item in trees.items()},
        "spacesSeparated": True,
        "textRecords": attempted,
        "skippedNonText": skipped_non_text,
        "labeledCounts": labeled_counts,
        "unknownCounts": unknown_counts,
        "meanLabelsPerRecord": {
            space: round(sum(label_counts[space]) / max(1, len(label_counts[space])), 3)
            for space in trees
        },
        "meanConfidence": {
            space: round(confidence_sum[space] / max(1, labeled_counts[space]), 6)
            for space in trees
        },
        "pathLegalRate": round(1 - invalid_labels / max(1, total_labels), 6),
        "unknownLabel": cfg["labeling"]["unknownLabel"],
        "modelVersion": model.model_version,
        "annotation": {
            "accuracy": None,
            "blockedReason": "MATCHING_ANNOTATION_REQUIRED",
            "note": "无人工标注（H-05）；不填准确率/混淆矩阵。",
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
        "treeVersion": metrics["treeVersion"],
        "treeHash": metrics["treeHash"],
        "treeSnapshotPath": next(iter(trees.values())).snapshot_path.as_posix() if trees else None,
        "paramsHash": f"sha256:{params_hash(resolved_params)}",
        "seed": resolved_seed,
        "sampleCount": attempted,
        "successCount": sum(1 for row in result_rows if not row.get("unclassified")),
        "failedCount": len(failures),
        "inputBytes": records_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / records_bytes, 6) if records_bytes else 0.0,
        "artifacts": payload_artifacts,
        "failedSamples": failures[:500],
        "createdAt": now_iso(),
        "notes": [
            "领域树与能力树分别向量化、分别阈值裁剪，标签空间不混用。",
            "无人工标注时不填准确率；未达阈值输出「未明确」。",
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
        "sampleCount": attempted,
        "successCount": manifest["successCount"],
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
        "sampleCount": attempted,
        "successCount": manifest["successCount"],
        "failedCount": len(failures),
        "failedSamples": failures[:500],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "多标签为独立空间裁剪，可跨领域；未达阈值输出「未明确」。",
            "零样本方法与 OP-05 一致，准确率需人工标注后评测。",
        ],
    }


def _labels_for_space(
    vector: np.ndarray,
    matrix: np.ndarray,
    space_tree,
    model,
    cfg: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labeling = cfg["labeling"]
    similarities = matrix @ vector
    order = np.argsort(-similarities)
    top_k = max(1, int(labeling["topK"]))
    top_indices = order[:top_k]
    top_sims = similarities[top_indices]
    temperature = max(float(labeling["temperature"]), 1e-6)
    shifted = top_sims - float(top_sims.max())
    probabilities = np.exp(shifted / temperature)
    probabilities = probabilities / probabilities.sum()
    top = [
        {
            "path": space_tree.labels[int(index)]["path"],
            "confidence": round(float(probabilities[position]), 6),
            "similarity": round(float(similarities[int(index)]), 6),
        }
        for position, index in enumerate(top_indices)
    ]
    labels: list[dict[str, Any]] = []
    for position, index in enumerate(top_indices):
        similarity = float(similarities[int(index)])
        confidence = float(probabilities[position])
        if similarity < float(labeling["minSimilarity"]):
            continue
        if confidence < float(labeling["confidenceThreshold"]):
            continue
        labels.append(
            {
                "path": space_tree.labels[int(index)]["path"],
                "confidence": round(confidence, 6),
                "similarity": round(similarity, 6),
                "topK": top,
                "evidence": evidence,
                "modelVersion": model.model_version,
                "treeVersion": space_tree.tree_version,
            }
        )
        if len(labels) >= int(labeling["maxLabels"]):
            break
    return labels, top


def _apply_overrides(cfg: dict[str, Any], params: dict[str, Any]) -> None:
    if "max_labels" in params:
        cfg["labeling"]["maxLabels"] = max(1, min(10, int(params["max_labels"])))
    if "min_similarity" in params:
        cfg["labeling"]["minSimilarity"] = float(params["min_similarity"])
    if "max_records" in params:
        cfg["limits"]["maxRecords"] = max(1, int(params["max_records"]))
    if "device" in params:
        cfg["model"]["device"] = str(params["device"])


def _locate_records(input_path: str) -> tuple[Path, Path]:
    root = Path(input_path).resolve()
    if root.is_file():
        if root.suffix.lower() != ".jsonl":
            raise ValueError(f"只接受 .jsonl 记录文件，实际 {root.name}")
        return root, root.parent
    for candidate in (
        root / "records.jsonl", root / "result.jsonl", root / "output" / "records.jsonl",
    ):
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
                "type": {".jsonl": "jsonl", ".json": "json", ".npy": "vectors"}.get(
                    path.suffix.lower(), "file"
                ),
                "path": path.as_posix(),
                "sha256": file_hashes(path)[1],
                "bytes": path.stat().st_size,
            }
        )
    return artifacts


def _clean_output(output: Path) -> None:
    for name in (
        "result.jsonl", "failures.jsonl", "input_manifest.json", "metrics.json",
        "manifest.json", "summary.json",
    ):
        (output / name).unlink(missing_ok=True)
    for space in ("domain", "ability"):
        (output / f"label_vectors_{space}.npy").unlink(missing_ok=True)
        (output / f"label_ids_{space}.jsonl").unlink(missing_ok=True)


def _run_id(fingerprint: str, params: dict[str, Any], seed: int) -> str:
    return hashlib.sha256(
        f"{fingerprint}|{OPERATOR_VERSION}|{params_hash(params)}|{seed}".encode("utf-8")
    ).hexdigest()[:16]
