"""OP-20 知识图谱与向量索引（``tool_graph_vector_index_v1``）。

消费 OP-02 记录与 OP-03 向量：规则抽取实体/关系并导出图谱（JSONL + Neo4j Cypher），
复用 bge 向量构建确定性 IVF 索引，输出 topK 检索、recall@k 与 QPS。
Neo4j/FAISS 服务由平台部署；算子只产文件并如实报告服务状态。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from .utils import export as export_util
from .utils import extract as extract_util
from .utils import vector as vector_util
from .utils.common import (
    ensure_output_dir,
    ensure_under_roots,
    environment_roots,
    fingerprint_path,
    load_config,
    now_iso,
    params_hash,
    write_json,
    write_jsonl,
)

OPERATOR_ID = "dm-graph-indexing"
SEMANTIC_CODE = "tool_graph_vector_index_v1"
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
    input_fingerprint = fingerprint_path(input_path)

    records_path, labels_path, vectors_path = _resolve_sources(input_path, resolved)
    if vectors_path is None:
        return _blocked(
            output, input_fingerprint, "VECTORS_REQUIRED",
            "缺少 OP-03 向量目录（params.vectors_path），OP-20 依赖 OP-03", cfg, resolved_seed, resolved,
        )
    records, failures = extract_util.load_records(records_path, int(cfg["limits"]["maxRecords"]))
    if not records:
        return _blocked(output, input_fingerprint, "RECORDS_EMPTY", "OP-02 记录为空", cfg, resolved_seed, resolved)
    labels = extract_util.load_labels(labels_path)
    graph = extract_util.build_graph(records, labels, cfg)
    if len(graph["nodes"]) > int(cfg["limits"]["maxEntities"]) + len(records) * 2:
        return _blocked(
            output, input_fingerprint, "GRAPH_TOO_LARGE",
            "图谱节点数超过配置上限", cfg, resolved_seed, resolved,
            detail={"nodes": len(graph["nodes"]), "edges": len(graph["edges"])},
        )
    if len(graph["edges"]) > int(cfg["limits"]["maxEdges"]):
        return _blocked(
            output, input_fingerprint, "EDGE_LIMIT_EXCEEDED",
            "图谱边数超过配置上限", cfg, resolved_seed, resolved,
            detail={"edges": len(graph["edges"])},
        )
    files = export_util.write_graph(output, graph)

    vectors, ids = vector_util.load_vectors(
        vectors_path / cfg["vector"]["relativePath"],
        vectors_path / cfg["vector"]["idsFile"],
        int(cfg["vector"]["dimension"]),
    )
    index = vector_util.build_index(vectors, ids, cfg, resolved_seed, output)
    write_jsonl(output / "query_results.jsonl", index["results"])

    services = {
        "neo4j": _service_status(cfg["services"]["neo4jUrlEnv"]),
        "faiss": _service_status(cfg["services"]["faissUrlEnv"]),
    }
    write_jsonl(output / "failures.jsonl", failures)

    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    run_id = _run_id(input_fingerprint, resolved, resolved_seed)
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "treeVersion": None,
        "graph": graph["stats"],
        "vector": {
            "indexVersion": index["meta"]["indexVersion"],
            "count": index["meta"]["count"],
            "dimension": index["meta"]["dimension"],
            "nlist": index["meta"]["nlist"],
            "nprobe": index["meta"]["nprobe"],
            "topK": index["meta"]["topK"],
            "queryCount": index["meta"]["queryCount"],
            "recallAtK": index["meta"]["recallAtK"],
            "qps": index["meta"]["qps"],
            "buildSeconds": index["meta"]["buildSeconds"],
        },
        "services": services,
        "ruleBased": True,
        "provisional": True,
        "deterministic": True,
        "runtimeSec": round(time.time() - started, 3),
        "generatedAt": now_iso(),
    }
    write_json(output / "metrics.json", metrics)
    write_json(output / "graph_stats.json", graph["stats"])
    write_json(
        output / "input_manifest.json",
        {
            "inputFingerprint": f"sha256:{input_fingerprint}",
            "recordsPath": records_path.as_posix(),
            "recordsFingerprint": f"sha256:{hashlib.sha256(records_path.read_bytes()).hexdigest()}",
            "labelsPath": labels_path.as_posix() if labels_path else None,
            "vectorsPath": vectors_path.as_posix(),
            "records": len(records),
            "labels": len(labels),
            "vectors": int(vectors.shape[0]),
            "dimension": int(vectors.shape[1]),
            "note": "实体/关系为规则抽取（H-11 本体/KG 未提供）；向量复用 OP-03。",
        },
    )
    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(resolved)}",
        "seed": resolved_seed,
        "sampleCount": len(records),
        "successCount": len(records),
        "failedCount": len(failures),
        "graph": {"nodes": graph["stats"]["nodeCount"], "edges": graph["stats"]["edgeCount"], **files},
        "vector": {"indexVersion": index["meta"]["indexVersion"], "files": index["meta"]["files"]},
        "services": services,
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "notes": [
            "实体/关系为可解释规则抽取，不是本体实体链接；标 ruleBased=true。",
            "IVF 近似索引以精确内积为金标准计算 recall@k；固定 seed 重建幂等。",
            "Neo4j/FAISS 服务由平台部署，算子只产导入文件/索引文件并报告服务状态。",
        ],
    }
    write_json(output / "manifest.json", manifest)
    write_json(
        output / "summary.json",
        {
            "operatorId": OPERATOR_ID,
            "semanticCode": SEMANTIC_CODE,
            "operatorVersion": OPERATOR_VERSION,
            "runId": run_id,
            "inputFingerprint": manifest["inputFingerprint"],
            "paramsHash": manifest["paramsHash"],
            "seed": resolved_seed,
            "modelVersion": None,
            "treeVersion": None,
            "sampleCount": len(records),
            "successCount": len(records),
            "failedCount": len(failures),
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )

    return {
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": len(records),
        "successCount": len(records),
        "failedCount": len(failures),
        "failedSamples": failures[:100],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": (output / "graph_nodes.jsonl").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "result": {
            "graph": graph["stats"],
            "index": index["meta"],
            "services": services,
            "files": files,
            "querySample": index["results"][:3],
        },
        "notes": [
            "图谱 nodes/edges/cypher 见 graph_nodes.jsonl、graph_edges.jsonl、neo4j_import.cypher。",
            "索引与检索见 index/、query_results.jsonl；服务状态见 metrics.services。",
        ],
    }


def _resolve_sources(input_path: str, params: dict[str, Any]) -> tuple[Path, Path | None, Path | None]:
    path = Path(input_path).resolve()
    payload: dict[str, Any] = {}
    if path.is_file() and path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif path.is_dir() and (path / "bundle.json").is_file():
        payload = json.loads((path / "bundle.json").read_text(encoding="utf-8"))
    roots = environment_roots()

    def resolve(raw: Any, name: str, required: bool) -> Path | None:
        if not raw:
            if required:
                raise ValueError(f"缺少 {name}")
            return None
        return ensure_under_roots(str(raw), roots)

    records_raw = params.get("records_path") or payload.get("recordsPath") or input_path
    records_root = resolve(records_raw, "records_path", True)
    labels_raw = params.get("labels_path") or payload.get("labelsPath")
    vectors_raw = params.get("vectors_path") or payload.get("vectorsPath")
    labels_root = resolve(labels_raw, "labels_path", False)
    vectors_root = resolve(vectors_raw, "vectors_path", False)
    records_path = records_root / "records.jsonl" if records_root.is_dir() else records_root
    labels_path = None
    if labels_root is not None:
        labels_path = labels_root / "result.jsonl" if labels_root.is_dir() else labels_root
    return records_path, labels_path, vectors_root


def _service_status(env_key: str) -> dict[str, Any]:
    configured = bool(os.getenv(env_key))
    return {
        "status": "configured" if configured else "unavailable",
        "reasonCode": None if configured else "SERVICE_NOT_CONFIGURED",
        "env": env_key,
        "note": "平台负责部署与联调；算子不发起网络连接。",
    }


def _blocked(
    output: Path,
    input_fingerprint: str,
    reason: str,
    message: str,
    cfg: dict[str, Any],
    seed: int,
    params: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _run_id(input_fingerprint, params, seed)
    metrics = {
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "runId": run_id,
        "paramsHash": f"sha256:{params_hash(params)}",
        "seed": seed,
        "treeVersion": None,
        "blockedReason": reason,
        "message": message,
        "detail": detail or {},
        "provisional": True,
        "deterministic": True,
        "generatedAt": now_iso(),
    }
    write_json(output / "metrics.json", metrics)
    artifacts = _collect_artifacts(output, exclude={"manifest.json", "summary.json", "result.json", "error.log"})
    manifest = {
        "runId": run_id,
        "inputFingerprint": f"sha256:{input_fingerprint}",
        "operatorId": OPERATOR_ID,
        "semanticCode": SEMANTIC_CODE,
        "operatorVersion": OPERATOR_VERSION,
        "modelVersion": None,
        "treeVersion": None,
        "paramsHash": f"sha256:{params_hash(params)}",
        "seed": seed,
        "sampleCount": 0,
        "successCount": 0,
        "failedCount": 0,
        "artifacts": artifacts,
        "createdAt": now_iso(),
        "blockedReason": reason,
    }
    write_json(output / "manifest.json", manifest)
    write_json(
        output / "summary.json",
        {
            "operatorId": OPERATOR_ID,
            "semanticCode": SEMANTIC_CODE,
            "operatorVersion": OPERATOR_VERSION,
            "runId": run_id,
            "inputFingerprint": manifest["inputFingerprint"],
            "paramsHash": manifest["paramsHash"],
            "seed": seed,
            "modelVersion": None,
            "treeVersion": None,
            "sampleCount": 0,
            "successCount": 0,
            "failedCount": 0,
            "metrics": metrics,
            "provisional": True,
            "generatedAt": now_iso(),
        },
    )
    return {
        "modelVersion": None,
        "treeVersion": None,
        "sampleCount": 0,
        "successCount": 0,
        "failedCount": 0,
        "failedSamples": [],
        "metrics": metrics,
        "artifacts": artifacts,
        "outputFilePath": (output / "graph_nodes.jsonl").as_posix(),
        "outputDir": output.as_posix(),
        "deterministic": True,
        "provisional": True,
        "blockedReason": reason,
        "notes": [message, "未构建图谱/索引，不伪造产物。"],
    }


def _collect_artifacts(output: Path, exclude: set[str]) -> list[dict[str, Any]]:
    items = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name in exclude or path.name.endswith(".tmp"):
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
