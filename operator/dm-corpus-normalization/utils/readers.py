"""读取 OP-01 产物：定位 result.jsonl、上游 manifest、逐行流式读取、源文件定位。

OP-02 只消费 OP-01 的文件契约，不 import OP-01 代码。源文件优先按记录里的
``metadata.extra.sourcePath`` 定位（绝对路径，由 OP-01 写入），其次按
``输入目录 / metadata.extra.file`` 定位。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from .common import read_json


class RecordsNotFound(ValueError):
    """输入中没有可识别的算子记录文件。"""


def locate_records(input_path: str | Path) -> tuple[Path, Path, dict[str, Any] | None]:
    """返回 (records 文件, 记录根目录, 上游 manifest 或 None)。"""

    root = Path(input_path).resolve()
    if root.is_file():
        if root.suffix.lower() != ".jsonl":
            raise RecordsNotFound(f"只接受 .jsonl 记录文件，实际 {root.name}")
        records_root = root.parent
    else:
        candidates = [
            root / "result.jsonl",
            root / "records.jsonl",
            root / "output" / "result.jsonl",
            root / "output" / "records.jsonl",
        ]
        existing = [item for item in candidates if item.is_file()]
        if not existing:
            existing = sorted(root.glob("*.jsonl"))
        if not existing:
            raise RecordsNotFound(f"目录中没有 result.jsonl/records.jsonl：{root}")
        records_root = existing[0].parent
    manifest = None
    for candidate in (records_root / "manifest.json", records_root.parent / "manifest.json"):
        if candidate.is_file():
            try:
                manifest = read_json(candidate)
            except (OSError, json.JSONDecodeError):
                manifest = None
            break
    records_path = root if root.is_file() else existing[0]
    return records_path, records_root, manifest


def iter_records(path: Path, max_records: int) -> Iterator[tuple[int, dict[str, Any] | None, str | None]]:
    """逐行读取；返回 (行号, 记录或 None, 错误信息)。"""

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


def resolve_source(
    record: dict[str, Any], records_root: Path, source_root: Path | None = None
) -> Path | None:
    """按记录溯源到原始文件；不存在或不支持返回 None。

    优先顺序：记录内的绝对 ``sourcePath`` → ``source_root``（显式参数）→ 记录根目录。
    """

    extra = (record.get("metadata") or {}).get("extra") or {}
    candidates: list[Path] = []
    source_path = extra.get("sourcePath")
    if isinstance(source_path, str) and source_path:
        candidate = Path(source_path)
        if candidate.is_absolute():
            candidates.append(candidate)
    relative = extra.get("file")
    if isinstance(relative, str) and relative:
        if source_root is not None:
            candidates.append(source_root / relative)
        candidates.append(records_root / relative)
    for candidate in candidates:
        try:
            if candidate.is_file() and not candidate.is_symlink():
                return candidate.resolve()
        except OSError:
            continue
    return None
