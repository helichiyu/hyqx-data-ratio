"""术语匹配与知识密度。

- 术语表为 jsonl ``{term, category}``；用 Aho–Corasick 自动机单遍匹配；
- 覆盖率 = 命中的不同术语数 / 术语表术语数；
- 知识密度 = 术语命中次数 / 文本长度 × 100（每百字）。
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any


class Automaton:
    """Aho–Corasick：节点为 dict，``fail`` 为失败指针，``output`` 为术语列表。"""

    def __init__(self, terms: list[str]) -> None:
        self.nodes: list[dict[str, Any]] = [{"next": {}, "fail": None, "output": []}]
        for term in terms:
            self._add(term)
        self._build()

    def _add(self, term: str) -> None:
        node = 0
        for char in term:
            nxt = self.nodes[node]["next"].get(char)
            if nxt is None:
                self.nodes.append({"next": {}, "fail": None, "output": []})
                nxt = len(self.nodes) - 1
                self.nodes[node]["next"][char] = nxt
            node = nxt
        self.nodes[node]["output"].append(term)

    def _build(self) -> None:
        queue: deque[int] = deque()
        for child in self.nodes[0]["next"].values():
            self.nodes[child]["fail"] = 0
            queue.append(child)
        while queue:
            current = queue.popleft()
            for char, nxt in self.nodes[current]["next"].items():
                fail = self.nodes[current]["fail"]
                while fail and char not in self.nodes[fail]["next"]:
                    fail = self.nodes[fail]["fail"]
                target = self.nodes[fail]["next"].get(char, 0) if fail else self.nodes[0]["next"].get(char, 0)
                if target == nxt:
                    target = 0
                self.nodes[nxt]["fail"] = target
                self.nodes[nxt]["output"].extend(self.nodes[target]["output"])
                queue.append(nxt)

    def find(self, text: str) -> list[str]:
        hits: list[str] = []
        node = 0
        for char in text:
            while node and char not in self.nodes[node]["next"]:
                node = self.nodes[node]["fail"]
            node = self.nodes[node]["next"].get(char, 0)
            if self.nodes[node]["output"]:
                hits.extend(self.nodes[node]["output"])
        return hits


def load_glossary(path: Path | None, max_terms: int) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    terms: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            term = row.get("term")
            if isinstance(term, str) and term:
                terms[term] = str(row.get("category") or "general")
            if len(terms) >= max_terms:
                break
    return terms


def analyze(text: str, automaton: Automaton | None, glossary: dict[str, str]) -> dict[str, Any]:
    if automaton is None or not glossary:
        return {
            "status": "unavailable",
            "reasonCode": "GLOSSARY_UNAVAILABLE",
            "hitCount": 0,
            "matchedTerms": 0,
            "coverage": None,
            "densityPer100Chars": None,
        }
    hits = automaton.find(text)
    unique = set(hits)
    return {
        "status": "ok",
        "reasonCode": None,
        "hitCount": len(hits),
        "matchedTerms": len(unique),
        "coverage": round(len(unique) / len(glossary), 6),
        "densityPer100Chars": round(len(hits) / len(text) * 100, 6) if text else None,
        "topTerms": sorted(unique)[:10],
        "allMatched": sorted(unique),
    }
