"""成品 Parquet 分片写出与文件对账。

按 ``modal/source/dt`` 分区、zstd 压缩、``maxRowsPerShard`` 分片、``rowGroupRows``
控制 row group；每个文件写完后立即计算字节/MD5/SHA-256，manifest 与磁盘逐项对账。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .common import file_hashes

SCHEMA = pa.schema(
    [
        ("record_id", pa.string()),
        ("label", pa.string()),
        ("level1", pa.string()),
        ("level2", pa.string()),
        ("confidence", pa.float64()),
        ("selection_rank", pa.int64()),
        ("modal", pa.string()),
        ("source", pa.string()),
        ("dt", pa.string()),
        ("text", pa.string()),
        ("metadata_json", pa.string()),
        ("quality_json", pa.string()),
        ("partitions_json", pa.string()),
        ("hashes_json", pa.string()),
    ]
)

_UNSAFE = re.compile(r"[^0-9A-Za-z一-鿿._-]+")


def _segment(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "").strip() or fallback
    text = text.replace("/", "_").replace("\\", "_")
    text = _UNSAFE.sub("_", text)
    if text in {".", ".."} or not text:
        text = fallback
    return text[:80]


def _partition(record: dict[str, Any]) -> tuple[str, str, str]:
    partitions = record.get("partitions") or {}
    modal = partitions.get("modal") or record.get("modal") or "unknown"
    source = partitions.get("source") or record.get("source") or "unknown"
    dt = partitions.get("dt") or "unknown"
    return _segment(modal), _segment(source), _segment(dt)


def _row(record: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": item["record_id"],
        "label": item["label"],
        "level1": item.get("level1"),
        "level2": item.get("level2"),
        "confidence": float(item.get("confidence") or 0.0),
        "selection_rank": int(item.get("selectionRank") or 0),
        "modal": (record.get("partitions") or {}).get("modal") or record.get("modal"),
        "source": record.get("source"),
        "dt": (record.get("partitions") or {}).get("dt"),
        "text": record.get("text"),
        "metadata_json": json.dumps(record.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
        "quality_json": json.dumps(record.get("quality") or {}, ensure_ascii=False, sort_keys=True),
        "partitions_json": json.dumps(record.get("partitions") or {}, ensure_ascii=False, sort_keys=True),
        "hashes_json": json.dumps(record.get("hashes") or {}, ensure_ascii=False, sort_keys=True),
    }


def write_dataset(
    output: Path,
    selected: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    dataset_dir = output / cfg["outputs"]["datasetDir"]
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for old in dataset_dir.rglob("*.parquet"):
        old.unlink()

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in selected:
        record = records.get(item["record_id"]) or {}
        groups[_partition(record)].append(_row(record, item))

    max_rows = int(cfg["parquet"]["maxRowsPerShard"])
    row_group_rows = int(cfg["parquet"]["rowGroupRows"])
    compression = str(cfg["parquet"]["compression"])
    files: list[dict[str, Any]] = []
    partition_counts: dict[str, int] = {}
    max_shards = int(cfg["limits"]["maxShards"])

    for (modal, source, dt), rows in sorted(groups.items()):
        partition_key = f"modal={modal}/source={source}/dt={dt}"
        partition_dir = dataset_dir / f"modal={modal}" / f"source={source}" / f"dt={dt}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        partition_counts[partition_key] = len(rows)
        for shard_index, start in enumerate(range(0, len(rows), max_rows)):
            chunk = rows[start : start + max_rows]
            relative = f"{partition_key}/part-{shard_index:05d}.parquet"
            path = dataset_dir / f"modal={modal}" / f"source={source}" / f"dt={dt}" / f"part-{shard_index:05d}.parquet"
            table = pa.Table.from_pylist(chunk, schema=SCHEMA)
            pq.write_table(table, path, compression=compression, row_group_size=row_group_rows)
            relative = path.relative_to(output).as_posix()
            if len(files) + 1 > max_shards:
                raise ValueError(f"分片数超过上限 {max_shards}")
            md5, sha256 = file_hashes(path)
            files.append(
                {
                    "path": relative,
                    "partition": partition_key,
                    "rows": table.num_rows,
                    "bytes": path.stat().st_size,
                    "md5": md5,
                    "sha256": sha256,
                }
            )

    total_rows = sum(item["rows"] for item in files)
    total_bytes = sum(item["bytes"] for item in files)
    if total_rows != len(selected):
        raise ValueError(f"Parquet 行数 {total_rows} 与选样数 {len(selected)} 不一致")
    return {
        "files": files,
        "fileCount": len(files),
        "partitionCounts": partition_counts,
        "rows": total_rows,
        "bytes": total_bytes,
        "compression": compression,
        "rowGroupRows": row_group_rows,
        "maxRowsPerShard": max_rows,
    }
