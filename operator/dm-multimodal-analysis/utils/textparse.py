"""文本与 PDF 解析：编码探测、乱码率、jsonl/json/xml/csv/txt、PDF 页文本与扫描页识别。

口径：
- 乱码率 =（U+FFFD 替换字符 + C0 控制字符 + 典型乱码片段 ``Ã``/``Â``/``â€``）出现次数 / 字符总数；
- 扫描页 = 页文本字符数 < 阈值且页面含图像；
- OCR 后端不可用时如实标记 ``OCR_BACKEND_UNAVAILABLE``，不生成文本。
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SUSPICIOUS = ("Ã", "Â", "â€")


def analyze_text(text: str) -> dict[str, Any]:
    total = len(text)
    if total == 0:
        return {"chars": 0, "mojibakeRate": 0.0, "controlChars": 0, "empty": True}
    replacements = text.count("�")
    controls = sum(
        1 for char in text if ord(char) < 32 and char not in ("\t", "\n", "\r")
    )
    suspicious = sum(text.count(item) for item in _SUSPICIOUS)
    rate = (replacements + controls + suspicious) / total
    return {
        "chars": total,
        "mojibakeRate": round(rate, 6),
        "controlChars": controls,
        "empty": not text.strip(),
    }


def decode_bytes(data: bytes, encodings: list[str]) -> dict[str, Any]:
    """按配置顺序严格解码；全部失败时用 latin-1 兜底并登记。"""

    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        stats = analyze_text(text)
        note = None
        if encoding == "latin-1" and stats["mojibakeRate"] > 0.02:
            note = "UNDECODED_LATIN1_FALLBACK"
        return {
            "text": text,
            "encoding": encoding,
            "decodeError": note,
            **stats,
        }
    text = data.decode("latin-1", errors="replace")
    stats = analyze_text(text)
    return {
        "text": text,
        "encoding": "latin-1-replace",
        "decodeError": "DECODE_FAILED",
        **stats,
    }


def parse_text_file(path: Path, cfg: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    """返回 ``records`` / ``failures`` / ``fileStats``；记录只含抽取后的文本与行号。"""

    data = path.read_bytes()
    decoded = decode_bytes(data, cfg["text"]["encodings"])
    text = decoded["text"]
    suffix = path.suffix.lower()
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    if suffix == ".jsonl":
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                failures.append(
                    {
                        "id": f"{path.name}:{number}",
                        "reasonCode": "JSONL_PARSE_FAILED",
                        "detail": f"第 {number} 行：{exc.msg}",
                    }
                )
                continue
            records.append(
                {
                    "text": _extract_text(payload, cfg["text"]["textFields"]),
                    "line": number,
                    "fields": list(payload) if isinstance(payload, dict) else []
                }
            )
    elif suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            failures.append(
                {"id": path.name, "reasonCode": "JSON_PARSE_FAILED", "detail": exc.msg}
            )
        else:
            items = payload if isinstance(payload, list) else [payload]
            for index, item in enumerate(items):
                records.append(
                    {
                        "text": _extract_text(item, cfg["text"]["textFields"]),
                        "line": index + 1,
                        "fields": list(item) if isinstance(item, dict) else []
                    }
                )
    elif suffix == ".xml":
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as exc:
            failures.append(
                {"id": path.name, "reasonCode": "XML_PARSE_FAILED", "detail": str(exc)}
            )
        else:
            records.append(
                {
                    "text": " ".join(part.strip() for part in root.itertext() if part.strip()),
                    "line": 1,
                    "fields": []
                }
            )
    elif suffix in (".csv", ".tsv"):
        delimiter = "," if suffix == ".csv" else "\t"
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        for number, row in enumerate(reader, start=1):
            joined = " | ".join(cell.strip() for cell in row if cell.strip())
            if joined:
                records.append({"text": joined, "line": number, "fields": []})
    else:
        records.append({"text": text, "line": 1, "fields": []})

    for record in records:
        if len(record["text"]) > max_chars:
            record["text"] = record["text"][:max_chars]
            record["truncated"] = True

    file_stats = {
        "encoding": decoded["encoding"],
        "decodeError": decoded["decodeError"],
        "mojibakeRate": decoded["mojibakeRate"],
        "chars": decoded["chars"],
        "emptyText": decoded["empty"],
    }
    return {"records": records, "failures": failures, "fileStats": file_stats}


def parse_pdf(path: Path, cfg: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    """PDF 页文本抽取与扫描页识别；PyMuPDF 不可用时抛 ImportError 由调用方转 reasonCode。"""

    try:
        import pymupdf  # type: ignore
    except ImportError:  # pragma: no cover - 镜像内必装
        import fitz as pymupdf  # type: ignore

    pdf_cfg = cfg["pdf"]
    limits = cfg["limits"]
    document = pymupdf.open(path)
    pages: list[dict[str, Any]] = []
    texts: list[str] = []
    scanned_pages: list[int] = []
    empty_pages: list[int] = []
    block_pages = 0
    font_sizes: dict[str, int] = {}

    try:
        page_count = document.page_count
        for index in range(page_count):
            page = document.load_page(index)
            page_text = page.get_text("text") or ""
            image_count = len(page.get_images(full=True))
            scanned = (
                len(page_text.strip()) < int(pdf_cfg["scannedPageMinTextChars"])
                and image_count > 0
            )
            if scanned:
                scanned_pages.append(index + 1)
            if not page_text.strip():
                empty_pages.append(index + 1)
            texts.append(page_text)

            page_info: dict[str, Any] = {
                "page": index + 1,
                "chars": len(page_text),
                "images": image_count,
                "scanned": scanned,
            }
            if block_pages < int(limits["maxBlockPages"]):
                blocks = [
                    block for block in page.get_text("blocks")
                    if len(block) >= 5 and block[6] == 0
                ]
                page_info["blocks"] = len(blocks)
                if blocks:
                    page_info["meanBlockChars"] = round(
                        sum(len(str(block[4])) for block in blocks) / len(blocks), 2
                    )
                if block_pages < 50:
                    for block in page.get_text("dict").get("blocks", []):
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                size = str(round(float(span.get("size", 0)), 1))
                                font_sizes[size] = font_sizes.get(size, 0) + 1
                block_pages += 1
            pages.append(page_info)

        metadata = document.metadata or {}
        captured_at = _pdf_date(metadata.get("creationDate") or metadata.get("modDate"))
    finally:
        document.close()

    full_text = "\n".join(texts)
    truncated = len(full_text) > max_chars
    if truncated:
        full_text = full_text[:max_chars]
    stats = analyze_text(full_text)
    page_with_text = page_count - len(empty_pages)
    return {
        "text": full_text,
        "pages": pages,
        "pageCount": page_count,
        "scannedPages": scanned_pages,
        "emptyPages": empty_pages,
        "blockPages": block_pages,
        "fontSizes": dict(sorted(font_sizes.items(), key=lambda item: item[0])),
        "capturedAt": captured_at,
        "truncated": truncated,
        "fileStats": {
            "encoding": "pdf-text-layer",
            "decodeError": None,
            "mojibakeRate": stats["mojibakeRate"],
            "chars": stats["chars"],
            "emptyText": page_with_text == 0,
            "completeness": round(page_with_text / page_count, 6) if page_count else 0.0,
        },
    }


def _extract_text(payload: Any, fields: list[str]) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        parts = [str(payload[key]) for key in fields if payload.get(key) not in (None, "")]
        if parts:
            return "\n".join(parts)
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, list):
        return "\n".join(_extract_text(item, fields) for item in payload)
    return json.dumps(payload, ensure_ascii=False)


def _pdf_date(raw: str | None) -> str | None:
    """PDF 日期 ``D:YYYYMMDDHHmmSSOHH'mm'`` → ISO；无法解析返回 None。"""

    if not raw or not raw.startswith("D:"):
        return None
    digits = raw[2:16]
    try:
        stamp = datetime.strptime(digits[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return stamp.astimezone().isoformat(timespec="seconds")
