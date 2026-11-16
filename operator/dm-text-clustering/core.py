"""OP-03 句向量与主题聚类（``corpus_shard_embed_cluster_v1``）。

消费 OP-02 的 ``records.jsonl``：文本分块 → bge 向量 → K 搜索/轮廓系数 → KMeans
→ 簇规模与 c-TF-IDF 主题词。固定 seed 可复现；模型缺失返回 ``DEPENDENCY_UNAVAILABLE``。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from .utils import chunking, cluster, embedder
from .utils.common import (
    ensure_output_dir,
    fingerprint_file,
    load_config,
    now_iso,
    params_hash,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-text-clustering"
SEMANTIC_CODE = "corpus_shard_embed_cluster_v1"
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
    resolved_params = dict(params or {})
    resolved_seed = DEFAULT_SEED if seed is None else int(seed)
    _apply_overrides(cfg, resolved_params)
    output = ensure_output_dir(output_dir)
    _clean_output(output)

    records_path, records_root = _locate_records(input_path)
    max_records = int(resolved_params.get("max_records", 1_000_000))
    texts: list[str] = []
    record_ids: list[str] = []
    chunk_counts: list[int] = []
    chunk_texts: list[str] = []
    chunk_owner: list[int] = []
    failures: list[dict[str, Any]] = []
    skipped_non_text = 0
    attempted = 0

    for number, record, error in _iter_records(records_path, max_records):
        if error:
            attempted += 1
            failures.append(
                {"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": error}
            )
            continue
        assert record is not None
        if record.get("modal") != "text":
            skipped_non_text += 1
            continue
        attempted += 1
        text = (record.get("text") or "").strip()
        if not text:
            failures.append(
                {
                    "id": record.get("record_id") or f"line:{number}",
                    "reasonCode": "EMPTY_TEXT",
                    "detail": "文本为空或仅空白，无法生成向量",
                }
            )
            continue
        texts.append(text)
        record_ids.append(str(record.get("record_id") or f"line:{number}"))

    model = None
    vectors = None
    chunk_vectors = None
    if texts:
        model = embedder.Embedder(cfg)
        for record_index, record_text in enumerate(texts):
            chunks = chunking.split_chunks(record_text, model.tokenizer, cfg)
            chunk_counts.append(len(chunks))
            for chunk in chunks:
                chunk_texts.append(chunk)
                chunk_owner.append(record_index)
        if not chunk_texts:
            vectors = np.zeros((0, model.dimension), dtype=np.float32)
        else:
            matrix = model.encode(chunk_texts)
            vectors = _aggregate_records(matrix, chunk_owner, len(texts))
            if cfg["chunking"].get("keepChunkVectors"):
                chunk_vectors = matrix.astype(np.float16)

    if vectors is not None and len(vectors):
        clustering = cluster.cluster_vectors(
            vectors,
            seed=resolved_seed,
            cfg=cfg,
            fixed_k=resolved_params.get("k"),
        )
        labels = clustering["labels"]
        topics = cluster.ctfidf_topics(texts, labels, clustering["k"], cfg)
    else:
        clustering = {
            "k": 0,
            "labels": [],
            "silhouette": None,
            "search": [],
            "distances": [],
            "centroids": np.zeros((0, cfg["model"]["dimension"]), dtype=np.float32),
            "deterministic": True,
        }
        topics = {}

    result_rows = []
    cluster_members: dict[int, list[dict[str, Any]]] = {}
    for index, record_id in enumerate(record_ids):
        label = int(clustering["labels"][index]) if clustering["labels"] else None
        row = {
            "record_id": record_id,
            "cluster": label,
            "distance_to_centroid": (
                round(float(clustering["distances"][index]), 6)
                if clustering["distances"]
                else None
            ),
            "chunk_count": chunk_counts[index],
            "text_chars": len(texts[index]),
        }
        result_rows.append(row)
        if label is not None:
            cluster_members.setdefault(label, []).append(row)

    vectors_path = output / "vectors.npy"
    chunk_vectors_path = output / "chunk_vectors.npy"
    centroids_path = output / "centroids.npy"
    vector_ids_path = output / "vector_ids.jsonl"
    result_path = output / "result.jsonl"
    summary_path = output / "cluster_summary.json"
    failures_path = output / "failures.jsonl"
    input_manifest_path = output / "input_manifest.json"
    metrics_path = output / "metrics.json"
    manifest_path = output / "manifest.json"
    summary_json_path = output / "summary.json"

    if vectors is not None and len(vectors):
        np.save(vectors_path, vectors.astype(np.float16))
        np.save(centroids_path, np.asarray(clustering["centroids"], dtype=np.float32))
        if chunk_vectors is not None:
            np.save(chunk_vectors_path, chunk_vectors)
            write_jsonl(
                output / "chunk_manifest.jsonl",
                [
                    {
                        "row": row,
                        "record_id": record_ids[owner],
                        "chunk_index": chunk_index,
                    }
                    for row, (owner, chunk_index) in enumerate(_chunk_index_map(chunk_owner))
                ],
            )
        write_jsonl(
            vector_ids_path,
            [{"row": index, "record_id": record_id} for index, record_id in enumerate(record_ids)],
        )
        write_jsonl(result_path, result_rows)
    else:
        write_jsonl(result_path, [])
    write_jsonl(failures_path, failures)

    cluster_summary = {
        "treeVersion": None,
        "modelVersion": model.model_version if model else cfg["model"]["name"],
        "vectorDimension": int(cfg["model"]["dimension"]),
        "algorithm": cfg["clustering"]["algorithm"],
        "seed": resolved_seed,
        "k": clustering["k"],
        "silhouette": clustering["silhouette"],
        "search": clustering["search"],
        "clusters": [
            {
                "cluster": label,
                "size": len(members),
                "topTerms": topics.get(label, []),
                "representativeRecordIds": [
                    item["record_id"]
                    for item in sorted(members, key=lambda row: row["distance_to_centroid"])[:3]
                ],
                "maxDistance": max(item["distance_to_centroid"] for item in members),
            }
            for label, members in sorted(cluster_members.items())
        ],
        "generatedAt": now_iso(),
    }
    write_json(summary_path, cluster_summary)

    fingerprint, records_bytes = fingerprint_file(records_path)
    write_json(
        input_manifest_path,
        {
            "recordsPath": records_path.as_posix(),
            "recordsRoot": records_root.as_posix(),
            "recordsFingerprint": f"sha256:{fingerprint}",
            "recordsBytes": records_bytes,
            "note": "只消费 OP-02 records.jsonl；非文本记录跳过并在 metrics 计数。",
        },
    )

    sizes = [len(members) for members in cluster_members.values()]
    metrics = {
        "recordsRead": attempted + skipped_non_text,
        "textRecords": attempted,
        "skippedNonText": skipped_non_text,
        "clusteredRecords": len([label for label in clustering["labels"] if label is not None]),
        "failedCount": len(failures),
        "chunkCount": len(chunk_texts),
        "avgChunksPerRecord": round(len(chunk_texts) / len(texts), 3) if texts else 0.0,
        "vectorDimension": int(cfg["model"]["dimension"]),
        "storageDtype": cfg["model"]["storageDtype"],
        "modelVersion": cluster_summary["modelVersion"],
        "k": clustering["k"],
        "silhouette": clustering["silhouette"],
        "searchRange": _search_range(len(texts), cfg),
        "searchCandidates": len(clustering["search"]),
        "clusterSizes": {
            "min": min(sizes) if sizes else 0,
            "median": float(np.median(sizes)) if sizes else 0.0,
            "max": max(sizes) if sizes else 0,
            "mean": round(float(np.mean(sizes)), 3) if sizes else 0.0,
        },
        "topicClusters": len([label for label, terms in topics.items() if terms]),
        "failuresByReason": dict(sorted(Counter(item["reasonCode"] for item in failures).items())),
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(metrics_path, metrics)

    payload_artifacts = _collect_artifacts(
        output, exclude={"manifest.json", "summary.json", "result.json", "error.log"}
    )
    input_bytes = records_bytes
    output_bytes = sum(item["bytes"] for item in payload_artifacts)
    manifest = {
        "runId": _run_id(fingerprint, resolved_params, resolved_seed),
        "inputFingerprint": f"sha256:{fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": cluster_summary["modelVersion"],
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(resolved_params)}",
        "seed": resolved_seed,
        "sampleCount": attempted,
        "successCount": len(result_rows),
        "failedCount": len(failures),
        "inputBytes": input_bytes,
        "outputBytes": output_bytes,
        "compressionRatio": round(output_bytes / input_bytes, 6) if input_bytes else 0.0,
        "artifacts": payload_artifacts,
        "failedSamples": failures,
        "createdAt": now_iso(),
        "notes": [
            "模型 bge-base-zh-v1.5（MIT），权重在 operator/weights/shared/，运行期不联网。",
            "treeVersion=null：聚类不消费分类树。",
            "向量落盘 float16；聚类在 float32 上执行，固定 seed。",
            "跨硬件浮点差异可能导致簇边界微调；确定性以同机复算为准。",
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
        "sampleCount": attempted,
        "successCount": len(result_rows),
        "failedCount": len(failures),
        "metrics": metrics,
        "provisional": True,
        "generatedAt": now_iso(),
    }
    write_json(summary_json_path, summary)

    artifacts = _collect_artifacts(output, exclude={"result.json", "error.log"})
    return {
        "modelVersion": manifest["modelVersion"],
        "treeVersion": None,
        "sampleCount": attempted,
        "successCount": len(result_rows),
        "failedCount": len(failures),
        "failedSamples": failures,
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": result_path.as_posix(),
        "deterministic": True,
        "provisional": True,
        "notes": [
            "聚类指标来自真实文本与 bge 向量；无人工主题标注，主题词可解释性待人工抽查。",
            "K 搜索为粗网格 + 局部细化，范围与步长见 configs/cluster.json。",
        ],
    }


def _apply_overrides(cfg: dict[str, Any], params: dict[str, Any]) -> None:
    if "min_k" in params:
        cfg["clustering"]["minK"] = max(2, int(params["min_k"]))
    if "max_k" in params:
        cfg["clustering"]["maxK"] = max(2, int(params["max_k"]))
    if "batch_size" in params:
        cfg["model"]["batchSize"] = max(1, int(params["batch_size"]))
    if "device" in params:
        cfg["model"]["device"] = str(params["device"])
    if "keep_chunks" in params:
        cfg["chunking"]["keepChunkVectors"] = bool(params["keep_chunks"])


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
        root / "output" / "result.jsonl",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate, candidate.parent
    matches = sorted(root.glob("*.jsonl"))
    if matches:
        return matches[0], matches[0].parent
    raise FileNotFoundError(f"目录中没有 records.jsonl/result.jsonl：{root}")


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


def _aggregate_records(matrix: np.ndarray, owners: list[int], record_count: int) -> np.ndarray:
    sums = np.zeros((record_count, matrix.shape[1]), dtype=np.float32)
    counts = np.zeros(record_count, dtype=np.float32)
    for row, owner in enumerate(owners):
        sums[owner] += matrix[row]
        counts[owner] += 1
    counts[counts == 0] = 1.0
    averaged = sums / counts[:, None]
    norms = np.linalg.norm(averaged, axis=1, keepdims=True)
    return averaged / np.clip(norms, 1e-12, None)


def _search_range(n: int, cfg: dict[str, Any]) -> dict[str, Any]:
    import math

    lower = max(int(cfg["clustering"]["minK"]), int(math.ceil(math.sqrt(n / 2)))) if n else 0
    upper = min(int(cfg["clustering"]["maxK"]), int(math.floor(4 * math.sqrt(n))), n) if n else 0
    return {"lower": lower, "upper": upper, "n": n}


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
        "failures.jsonl",
        "vectors.npy",
        "chunk_vectors.npy",
        "centroids.npy",
        "vector_ids.jsonl",
        "chunk_manifest.jsonl",
        "cluster_summary.json",
        "input_manifest.json",
        "metrics.json",
        "manifest.json",
        "summary.json",
    ):
        (output / name).unlink(missing_ok=True)
    for name in ("chunks",):
        shutil.rmtree(output / name, ignore_errors=True)


def _run_id(fingerprint: str, params: dict[str, Any], seed: int) -> str:
    return hashlib.sha256(
        f"{fingerprint}|{OPERATOR_VERSION}|{params_hash(params)}|{seed}".encode("utf-8")
    ).hexdigest()[:16]


def _chunk_index_map(owners: list[int]) -> list[tuple[int, int]]:
    counters: dict[int, int] = {}
    result: list[tuple[int, int]] = []
    for owner in owners:
        index = counters.get(owner, 0)
        counters[owner] = index + 1
        result.append((owner, index))
    return result
