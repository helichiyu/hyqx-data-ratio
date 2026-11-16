"""标准记录校验与文本归一化。

校验口径与 ``docs/算子开发/schemas/record.schema.json``（S0 冻结）一致；镜像内不带
``docs/``，因此实现必填/枚举/哈希/分区格式的轻量校验。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

MODALS = {"text", "image", "audio", "video"}
SOURCES = {"web_text", "books", "code", "science", "wiki", "dialogue"}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_DT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_record(record: dict[str, Any]) -> list[str]:
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
    if not isinstance(partitions, dict) or set(partitions) != {"modal", "source", "dt"}:
        errors.append("partitions 必须且只能含 modal/source/dt")
    elif not _DT.fullmatch(str(partitions["dt"])):
        errors.append("partitions.dt 格式错误")
    hashes = record["hashes"]
    if not _HEX32.fullmatch(str(hashes.get("md5", ""))):
        errors.append("hashes.md5 格式错误")
    if not _HEX64.fullmatch(str(hashes.get("sha256", ""))):
        errors.append("hashes.sha256 格式错误")
    return errors


def normalize_text(text: str | None) -> tuple[str | None, dict[str, Any]]:
    """NFC 归一化、去控制字符、统一换行、折叠多余空行。"""

    if text is None:
        return None, {"changed": False, "chars": 0, "removedControlChars": 0}
    original = text
    normalized = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    removed = len(_CONTROL.findall(normalized))
    normalized = _CONTROL.sub("", normalized)
    lines = [line.rstrip() for line in normalized.split("\n")]
    collapsed: list[str] = []
    blank = 0
    for line in lines:
        if line:
            blank = 0
            collapsed.append(line)
        else:
            blank += 1
            if blank <= 1:
                collapsed.append("")
    normalized = "\n".join(collapsed).strip()
    return normalized, {
        "changed": normalized != original,
        "chars": len(normalized),
        "removedControlChars": removed,
    }
