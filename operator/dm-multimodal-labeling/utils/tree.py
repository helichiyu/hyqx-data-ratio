"""分类树快照加载：叶子路径、标签文本与路径合法性。"""

from __future__ import annotations

from typing import Any

from .common import read_json, resolve_operator_path


class LabelTree:
    def __init__(self, cfg: dict[str, Any]) -> None:
        tree_cfg = cfg["tree"]
        snapshot_path = resolve_operator_path(tree_cfg["relativePath"])
        if not snapshot_path.is_file():
            raise FileNotFoundError(f"树快照不存在：{snapshot_path}")
        snapshot = read_json(snapshot_path)
        self.tree_version = str(snapshot["treeVersion"])
        space = tree_cfg["space"]
        tree = snapshot["trees"][space]
        nodes = tree["nodes"]
        max_depth = max(int(node.get("depth", 0)) for node in nodes) if nodes else 0
        leaves = [
            node for node in nodes
            if bool(node.get("leaf")) or int(node.get("depth", 0)) >= max_depth
        ]
        if not tree_cfg.get("leafOnly", True):
            leaves = nodes
        self.labels: list[dict[str, Any]] = []
        self.paths: set[tuple[str, ...]] = set()
        for node in leaves:
            path = tuple(node["path"])
            self.paths.add(path)
            description = (node.get("description") or "").strip()
            text = " > ".join(path)
            if description:
                text = f"{text}：{description}"
            self.labels.append(
                {
                    "nodeId": node.get("nodeId"),
                    "path": list(path),
                    "name": node.get("name"),
                    "description": description,
                    "text": text,
                }
            )
        self.labels.sort(key=lambda item: tuple(item["path"]))
        self.label_texts = [item["text"] for item in self.labels]

    def is_valid(self, path: list[str]) -> bool:
        return tuple(path) in self.paths
