"""图谱导入文件导出：JSONL 与 Neo4j Cypher。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _cypher_string(value: Any) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
    return f"'{text}'"


def write_graph(output: Path, graph: dict[str, Any]) -> dict[str, Any]:
    nodes_path = output / "graph_nodes.jsonl"
    edges_path = output / "graph_edges.jsonl"
    nodes_path.parent.mkdir(parents=True, exist_ok=True)
    with nodes_path.open("w", encoding="utf-8", newline="\n") as sink:
        for node in graph["nodes"]:
            sink.write(json.dumps(node, ensure_ascii=False, sort_keys=True) + "\n")
    with edges_path.open("w", encoding="utf-8", newline="\n") as sink:
        for edge in graph["edges"]:
            sink.write(json.dumps(edge, ensure_ascii=False, sort_keys=True) + "\n")

    label_map = {"record": "Record", "label": "Label", "entity": "Entity"}
    cypher_path = output / "neo4j_import.cypher"
    with cypher_path.open("w", encoding="utf-8", newline="\n") as sink:
        for node in graph["nodes"]:
            node_label = label_map.get(str(node["type"]), "Node")
            properties = {"id": node["id"], "name": node["name"], **node.get("properties", {})}
            props = ", ".join(f"{key}: {_cypher_string(value)}" for key, value in properties.items())
            sink.write(f"MERGE (n:{node_label} {{id: {_cypher_string(node['id'])}}}) SET n += {{{props}}};\n")
        for edge in graph["edges"]:
            relation = str(edge["type"])
            sink.write(
                f"MATCH (a {{id: {_cypher_string(edge['source'])}}}), (b {{id: {_cypher_string(edge['target'])}}}) "
                f"MERGE (a)-[r:{relation}]->(b) SET r.weight = {float(edge['weight'])};\n"
            )
    return {
        "nodesFile": nodes_path.name,
        "edgesFile": edges_path.name,
        "cypherFile": cypher_path.name,
    }
