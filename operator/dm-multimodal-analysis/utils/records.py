"""标准记录组装与轻量校验。

字段口径见 ``docs/算子开发/schemas/record.schema.json``（S0 冻结）；镜像内不携带
``docs/``，因此这里实现同口径的必填/枚举/哈希校验，避免产物到下游才暴露错误。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

MODALS = {"text", "image", "audio", "video"}
SOURCES = {"web_text", "books", "code", "science", "wiki", "dialogue"}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_DT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def record_id_for_file(relative: str, sha256: str) -> str:
    digest = hashlib.sha256(f"{relative}\0{sha256}".encode("utf-8")).hexdigest()
    return f"r_{digest[:24]}"


def record_id_for_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"r_{digest[:24]}"


def make_record(
    *,
    record_id: str,
    modal: str,
    source: str,
    text: str | None,
    metadata: dict[str, Any],
    quality: dict[str, Any],
    partitions: dict[str, str],
    hashes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "modal": modal,
        "source": source,
        "text": text,
        "metadata": metadata,
        "quality": quality,
        "partitions": partitions,
        "hashes": hashes,
    }


def validate_record(record: dict[str, Any]) -> list[str]:
    """返回错误列表；空列表表示通过。只做 Schema 的必填/枚举/格式约束。"""

    errors: list[str] = []
    for key in ("record_id", "modal", "source", "metadata", "quality", "partitions", "hashes"):
        if key not in record:
            errors.append(f"缺少字段 {key}")
    if errors:
        return errors
    if record["modal"] not in MODALS:
        errors.append(f"非法 modal：{record['modal']}")
    if record["source"] not in SOURCES:
        errors.append(f"非法 source：{record['source']}")
    metadata = record["metadata"]
    for key in ("format", "sizeBytes", "sha256"):
        if key not in metadata:
            errors.append(f"metadata 缺少 {key}")
    if isinstance(metadata.get("sha256"), str) and not _HEX64.fullmatch(metadata["sha256"]):
        errors.append("metadata.sha256 格式错误")
    quality = record["quality"]
    if "decodable" not in quality or "completeness" not in quality:
        errors.append("quality 缺少 decodable/completeness")
    partitions = record["partitions"]
    if set(partitions) != {"modal", "source", "dt"}:
        errors.append("partitions 必须且只能含 modal/source/dt")
    else:
        if not _DT.fullmatch(str(partitions["dt"])):
            errors.append("partitions.dt 格式错误")
    hashes = record["hashes"]
    if not _HEX32.fullmatch(str(hashes.get("md5", ""))):
        errors.append("hashes.md5 格式错误")
    if not _HEX64.fullmatch(str(hashes.get("sha256", ""))):
        errors.append("hashes.sha256 格式错误")
    return errors


def artifact_entry(path: Path, artifact_type: str) -> dict[str, Any]:
    from .hashes import file_hashes

    _, sha256 = file_hashes(path)
    return {
        "type": artifact_type,
        "path": path.as_posix(),
        "sha256": sha256,
        "bytes": path.stat().st_size,
    }
