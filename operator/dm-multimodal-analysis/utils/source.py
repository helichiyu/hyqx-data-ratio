"""六类来源规则打分（OP-01 初判，最终口径由 OP-08 复算）。

来源分类以 ``operator/baseline/source-map.json`` 为准（``sourceClassVersion``）；
本模块只做规则打分，不训练、不调用模型，打分与命中证据一并写入记录。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .common import PACKAGE_DIR

_SOURCE_MAP_PATH = PACKAGE_DIR.parent / "baseline" / "source-map.json"
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_CODE_LINE_RE = re.compile(
    r"^\s*(?:import\s+\w+|from\s+\w+\s+import|def\s+\w+\(|class\s+\w+[:(\[]|#include\s*<|"
    r"public\s+\w+|private\s+\w+|package\s+[\w.]+;|function\s+\w+\(|const\s+\w+\s*=)",
    re.MULTILINE,
)
_DIALOGUE_RE = re.compile(r"^\s*(?:User|Assistant|Human|AI|用户|助手|Q|A)\s*[:：]", re.MULTILINE)


@lru_cache(maxsize=1)
def _load_classes() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(_SOURCE_MAP_PATH.read_text(encoding="utf-8"))
    classes = payload["classes"]
    return payload, classes


def classify(
    path: Path,
    *,
    text: str | None,
    fields: list[str] | None = None,
    format_name: str | None = None,
) -> dict[str, Any]:
    """返回 ``source``（六类 alias）、``scores``、``evidence``、``sourceClassVersion``。"""

    payload, classes = _load_classes()
    scores: dict[str, float] = {item["alias"]: 0.0 for item in classes}
    evidence: list[dict[str, Any]] = []
    lowered_name = path.name.lower()
    suffix = path.suffix.lower()
    body = text or ""
    urls = " ".join(_URL_RE.findall(body[:20000]))
    haystack = f"{lowered_name} {urls}".lower()
    fields = fields or []

    for item in classes:
        alias = item["alias"]
        hints = item.get("ruleHints") or {}
        extensions = [ext.lower() for ext in hints.get("extensions", [])]
        if suffix and suffix in extensions:
            weight = 4.0 if alias == "code" else 2.5
            scores[alias] += weight
            evidence.append({"source": alias, "rule": "extension", "value": suffix, "weight": weight})
        for domain in hints.get("domains", []):
            if domain.lower() in haystack:
                scores[alias] += 3.0
                evidence.append({"source": alias, "rule": "domain", "value": domain, "weight": 3.0})
        for key in hints.get("metadataKeys", []):
            if key in fields:
                scores[alias] += 3.0
                evidence.append({"source": alias, "rule": "metadataKey", "value": key, "weight": 3.0})

    content_rules = _content_scores(body)
    for alias, weight, rule in content_rules:
        scores[alias] += weight
        evidence.append({"source": alias, "rule": rule, "value": None, "weight": weight})

    if format_name == "pdf":
        scores["books"] += 2.0
        evidence.append({"source": "books", "rule": "format", "value": "pdf", "weight": 2.0})
    elif format_name in {"jsonl", "json"}:
        scores["web_text"] += 0.5

    fallback = next((item["alias"] for item in classes if item.get("fallback")), "web_text")
    best = max(
        (item for item in classes),
        key=lambda item: (scores[item["alias"]], -float(item.get("precedence", 999))),
    )
    if scores[best["alias"]] <= 0:
        best_alias = fallback
        evidence.append({"source": fallback, "rule": "fallback", "value": None, "weight": 0.0})
    else:
        best_alias = best["alias"]

    return {
        "source": best_alias,
        "scores": {alias: round(value, 3) for alias, value in scores.items()},
        "evidence": evidence,
        "sourceClassVersion": payload.get("sourceClassVersion"),
    }


def _content_scores(text: str) -> list[tuple[str, float, str]]:
    if not text:
        return []
    sample = text[:200000]
    lowered = sample.lower()
    hits: list[tuple[str, float, str]] = []
    code_lines = len(_CODE_LINE_RE.findall(sample))
    line_count = max(1, sample.count("\n") + 1)
    if code_lines >= 3 and code_lines / line_count > 0.01:
        hits.append(("code", 3.5, "codeSyntaxRatio"))
    if len(_DIALOGUE_RE.findall(sample)) >= 2:
        hits.append(("dialogue", 4.0, "dialogueMarkers"))
    if "arxiv" in lowered or "doi:" in lowered or "abstract" in lowered:
        hits.append(("science", 2.5, "scienceMarkers"))
    if "wikipedia" in lowered or "维基百科" in sample or "wikimedia" in lowered:
        hits.append(("wiki", 3.0, "wikiMarkers"))
    if "isbn" in lowered or "出版社" in sample or "chapter" in lowered:
        hits.append(("books", 2.0, "bookMarkers"))
    return hits
