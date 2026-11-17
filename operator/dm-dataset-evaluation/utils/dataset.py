"""读取 OP-17 成品 manifest 与 Parquet 分片，恢复逐条记录。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"OP-17 运行目录缺少 manifest.json：{run_dir}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    dataset = payload.get("dataset") or {}
    if not dataset.get("files"):
        raise ValueError("OP-17 manifest.dataset.files 为空")
    return payload


def load_records(run_dir: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    expected = 0
    for item in manifest["dataset"]["files"]:
        path = run_dir / item["path"]
        if not path.is_file():
            raise FileNotFoundError(f"成品分片不存在：{path}")
        table = pq.read_table(path)
        expected += int(item.get("rows") or 0)
        for row in table.to_pylist():
            record_id = str(row.get("record_id") or "")
            if record_id:
                records[record_id] = row
    if expected and expected != len(records):
        raise ValueError(f"manifest 行数 {expected} 与 Parquet 读取 {len(records)} 不一致")
    return records
