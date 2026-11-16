"""模态识别：扩展名 + 魔数 + 容器特征交叉验证。

判定顺序（任务书 ING-01）：
1. 扩展名给出候选模态；
2. 文件头魔数（前 4 KiB）给出候选模态/格式；
3. ISO-BMFF（mp4/mov/m4a）与 RIFF（wav/webp/avi）按偏移量细分；
4. 两者一致置信度 0.99，仅魔数 0.90，仅扩展名 0.75；冲突以魔数为准并在证据中登记。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import load_config

_GROUP_OF_SUFFIX: dict[str, str] = {}
for _group, _suffixes in load_config("formats.json")["modalExtensions"].items():
    for _suffix in _suffixes:
        _GROUP_OF_SUFFIX[_suffix] = _group

_FORMATS = load_config("formats.json")
_CONFIDENCE = _FORMATS["confidence"]
_MAGIC = _FORMATS["magicSignatures"]
_RIFF = _FORMATS["riffSignatures"]
_BMFF = set(_FORMATS["isoBmffFormats"])
_MP3_SYNC = _FORMATS["mp3FrameSyncPrefix"]
_EXT_FORMAT = _FORMATS["extensionFormatHints"]
_MODAL_OF_GROUP: dict[str, str] = _FORMATS["modalOfGroup"]
_ARCHIVES = set(_FORMATS["archives"])


def detect(path: Path) -> dict[str, Any]:
    """返回 ``modal/format/confidence/evidence/conflicts``；无法判定时 modal=None。"""

    suffix = path.suffix.lower()
    head = _read_head(path)
    evidence: list[dict[str, Any]] = []
    conflicts: list[str] = []

    group = _GROUP_OF_SUFFIX.get(suffix)
    ext_modal = _MODAL_OF_GROUP.get(group) if group else None
    if group:
        evidence.append({"rule": "extension", "value": suffix, "supports": ext_modal, "group": group})

    magic_format, magic_modal, magic_hex = _sniff(head)
    if magic_format:
        evidence.append(
            {"rule": "magic", "value": magic_hex, "supports": magic_modal, "format": magic_format}
        )

    if suffix in _ARCHIVES or magic_format == "zip":
        return {
            "modal": None,
            "format": "zip",
            "confidence": 1.0,
            "evidence": evidence,
            "conflicts": conflicts,
            "archive": True,
        }

    modal: str | None
    confidence: float
    if magic_modal and ext_modal:
        modal = magic_modal
        confidence = _CONFIDENCE["extensionAndMagic"]
        if magic_modal != ext_modal:
            conflicts.append(f"扩展名指向 {ext_modal}，魔数指向 {magic_modal}，以魔数为准")
            confidence = _CONFIDENCE["magicOnly"]
    elif magic_modal:
        modal = magic_modal
        confidence = _CONFIDENCE["magicOnly"]
    elif ext_modal:
        modal = ext_modal
        confidence = _CONFIDENCE["extensionOnly"]
    else:
        modal = None
        confidence = _CONFIDENCE["unknown"]

    if modal is None:
        evidence.append({"rule": "fallback", "value": None, "supports": None})

    fmt = magic_format or _EXT_FORMAT.get(suffix) or (suffix.lstrip(".") or "unknown")
    return {
        "modal": modal,
        "format": fmt,
        "confidence": confidence,
        "evidence": evidence,
        "conflicts": conflicts,
        "archive": False,
    }


def _read_head(path: Path, size: int = 4096) -> bytes:
    with path.open("rb") as source:
        return source.read(size)


def _sniff(head: bytes) -> tuple[str | None, str | None, str | None]:
    for signature in _MAGIC:
        offset = int(signature.get("offset", 0))
        blob = bytes.fromhex(signature["hex"])
        if head[offset : offset + len(blob)] == blob:
            return signature["format"], signature.get("modal"), signature["hex"]
    if head[:4] == b"RIFF":
        for signature in _RIFF:
            offset = int(signature["offset"])
            blob = bytes.fromhex(signature["hex"])
            if head[offset : offset + len(blob)] == blob:
                return signature["format"], signature["modal"], f"RIFF/{signature['hex']}"
    if head[4:8] == b"ftyp":
        brand = head[8:12].decode("ascii", errors="replace").strip().lower()
        if brand in _BMFF:
            modal = "audio" if brand == "m4a" else "video"
            return brand, modal, "ftyp:" + brand
    if len(head) >= 2 and head[:2].hex() in _MP3_SYNC:
        return "mp3", "audio", head[:2].hex()
    return None, None, None


def supported_suffixes() -> set[str]:
    return set(_GROUP_OF_SUFFIX) | _ARCHIVES


def modal_confidence_ok(result: dict[str, Any], minimum: float) -> bool:
    return bool(result.get("modal")) and float(result.get("confidence") or 0) >= minimum
