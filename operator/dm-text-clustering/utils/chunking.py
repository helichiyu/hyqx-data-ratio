"""按 tokenizer 切窗：句末优先打包到 512 token，超长句再硬切。"""

from __future__ import annotations

import re
from typing import Any


def split_chunks(
    text: str, tokenizer: Any, cfg: dict[str, Any]
) -> list[str]:
    max_tokens = int(cfg["chunking"]["maxTokens"])
    splitter = re.compile(f"({cfg['chunking']['sentenceSplitPattern']})")
    if not text or not text.strip():
        return []
    pieces = splitter.split(text)
    sentences: list[str] = []
    buffer = ""
    for piece in pieces:
        if not piece:
            continue
        buffer += piece
        if splitter.fullmatch(piece):
            sentences.append(buffer)
            buffer = ""
    if buffer.strip():
        sentences.append(buffer)
    sentences = [item for item in sentences if item.strip()]
    if not sentences:
        sentences = [text]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        ids = tokenizer.encode(sentence, add_special_tokens=False)
        if len(ids) > max_tokens:
            if current:
                chunks.append("".join(current))
                current, current_tokens = [], 0
            for start in range(0, len(ids), max_tokens):
                piece = ids[start : start + max_tokens]
                chunks.append(tokenizer.decode(piece, skip_special_tokens=True))
            continue
        if current_tokens + len(ids) > max_tokens and current:
            chunks.append("".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += len(ids)
    if current:
        chunks.append("".join(current))
    min_chars = int(cfg["chunking"]["minCharsPerChunk"])
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= min_chars]


def chunk_record(
    text: str, tokenizer: Any, cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    return [{"text": chunk} for chunk in split_chunks(text, tokenizer, cfg)]
