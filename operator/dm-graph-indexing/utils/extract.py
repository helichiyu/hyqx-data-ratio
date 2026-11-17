"""规则实体/关系抽取与图谱构建。

H-11 未提供本体/KG/词表：用可解释正则抽取日期、数字、机构后缀、引号术语，
关系为记录-标签、记录-实体、一级-二级标签、同记录实体共现；
结果标 ``rule_based=true``，不冒充本体实体链接。
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_records(path: Path, max_records: int) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if len(records) >= max_records:
                failures.append({"id": f"line:{number}", "reasonCode": "RECORD_LIMIT_EXCEEDED"})
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append({"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": str(exc)})
                continue
            record_id = str(row.get("record_id") or "")
            if record_id:
                records[record_id] = row
    return records, failures


def load_labels(path: Path | None) -> dict[str, str]:
    labels: dict[str, str] = {}
    if path is None or not path.is_file():
        return labels
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            record_id = str(row.get("record_id") or "")
            candidates = []
            for label in row.get("labels") or []:
                if isinstance(label, dict) and isinstance(label.get("path"), list) and label["path"]:
                    path_text = "/".join(str(item) for item in label["path"])
                    candidates.append((float(label.get("confidence") or 0.0), path_text))
            if record_id and candidates:
                candidates.sort(key=lambda item: (-item[0], item[1]))
                labels[record_id] = candidates[0][1]
    return labels


def extract_entities(
    text: str,
    patterns: dict[str, list[str]],
    min_length: int,
    max_entities: int,
) -> list[dict[str, str]]:
    if not text:
        return []
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entity_type, regexes in patterns.items():
        for regex in regexes:
            try:
                matches = re.findall(regex, text)
            except re.error:
                continue
            for match in matches:
                value = match.strip().strip("“”\"'")
                if len(value) < min_length:
                    continue
                key = (entity_type, value)
                if key in seen:
                    continue
                seen.add(key)
                found.append({"type": entity_type, "text": value})
                if len(found) >= max_entities:
                    return found
    return found


def build_graph(
    records: dict[str, dict[str, Any]],
    labels: dict[str, str],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    patterns = cfg["entities"]["patterns"]
    min_length = int(cfg["entities"]["minTermLength"])
    max_entities = int(cfg["entities"]["maxEntitiesPerRecord"])
    max_pairs = int(cfg["relations"]["maxCooccurrencePairsPerRecord"])
    relation = cfg["relations"]

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    entity_stats: Counter[str] = Counter()
    skipped = 0

    def add_node(node_id: str, node_type: str, name: str, properties: dict[str, Any] | None = None) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": node_type, "name": name, "properties": properties or {}}

    def add_edge(source: str, target: str, edge_type: str, weight: float = 1.0) -> None:
        key = (source, target, edge_type)
        if key in edges:
            edges[key]["weight"] = round(float(edges[key]["weight"]) + weight, 6)
        else:
            edges[key] = {"source": source, "target": target, "type": edge_type, "weight": round(weight, 6)}

    for record_id, record in records.items():
        record_node = f"record:{record_id}"
        partitions = record.get("partitions") or {}
        add_node(
            record_node,
            "record",
            record_id,
            {
                "modal": partitions.get("modal") or record.get("modal"),
                "source": partitions.get("source") or record.get("source"),
                "dt": partitions.get("dt"),
            },
        )
        label = labels.get(record_id)
        if label:
            label_node = f"label:{label}"
            add_node(label_node, "label", label, {"level2": "/".join(label.split("/")[:2])})
            add_edge(record_node, label_node, relation["recordLabel"])
            parts = label.split("/")
            for depth in range(1, len(parts)):
                parent = "/".join(parts[:depth])
                child = "/".join(parts[: depth + 1])
                add_node(f"label:{parent}", "label", parent, {})
                add_node(f"label:{child}", "label", child, {})
                add_edge(f"label:{parent}", f"label:{child}", relation["labelParent"])

        entities = extract_entities(record.get("text") or "", patterns, min_length, max_entities)
        entity_ids = []
        for entity in entities:
            entity_id = f"entity:{entity['type']}:{entity['text']}"
            add_node(entity_id, "entity", entity["text"], {"entityType": entity["type"]})
            add_edge(record_node, entity_id, relation["recordEntity"])
            entity_stats[entity["type"]] += 1
            entity_ids.append(entity_id)
        for index, left in enumerate(sorted(entity_ids)):
            for right in sorted(entity_ids)[index + 1 : index + 1 + max_pairs]:
                add_edge(left, right, relation["cooccurrence"])

    node_list = sorted(nodes.values(), key=lambda item: item["id"])
    edge_list = sorted(edges.values(), key=lambda item: (item["source"], item["target"], item["type"]))
    node_counts = Counter(item["type"] for item in node_list)
    edge_counts = Counter(item["type"] for item in edge_list)
    return {
        "nodes": node_list,
        "edges": edge_list,
        "stats": {
            "recordCount": len(records),
            "labelCount": sum(1 for item in node_list if item["type"] == "label"),
            "entityCount": sum(1 for item in node_list if item["type"] == "entity"),
            "nodeCount": len(node_list),
            "edgeCount": len(edge_list),
            "nodesByType": dict(sorted(node_counts.items())),
            "edgesByType": dict(sorted(edge_counts.items())),
            "entitiesByType": dict(sorted(entity_stats.items())),
            "ruleBased": True,
            "skipped": skipped,
        },
    }
