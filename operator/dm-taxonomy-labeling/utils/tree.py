"""领域/能力树加载：两个标签空间分离，叶子路径与标签文本。"""

from __future__ import annotations

import hashlib
from typing import Any

from .common import (
    ensure_under_roots,
    environment_roots,
    read_json,
    resolve_operator_path,
)


class LabelTree:
    def __init__(
        self,
        snapshot_path: str,
        space: str,
        override_path: str | None = None,
        expected_version: str | None = None,
    ) -> None:
        if override_path:
            path = ensure_under_roots(override_path, environment_roots())
        else:
            path = resolve_operator_path(snapshot_path)
        if not path.is_file():
            raise FileNotFoundError(f"树快照不存在：{path}")
        snapshot = read_json(path)
        self.tree_version = str(snapshot["treeVersion"])
        if expected_version and expected_version != self.tree_version:
            raise ValueError(
                f"分类树版本不一致：要求 {expected_version}，快照为 {self.tree_version}"
            )
        self.tree_hash = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        self.snapshot_path = path
        self.space = space
        nodes = snapshot["trees"][space]["nodes"]
        max_depth = max(int(node.get("depth", 0)) for node in nodes) if nodes else 0
        leaves = [
            node for node in nodes
            if bool(node.get("leaf")) or int(node.get("depth", 0)) >= max_depth
        ]
        self.labels: list[dict[str, Any]] = []
        self.paths: set[tuple[str, ...]] = set()
        for node in leaves:
            path_tuple = tuple(node["path"])
            description = (node.get("description") or "").strip()
            text = " > ".join(path_tuple)
            if description:
                text = f"{text}：{description}"
            self.paths.add(path_tuple)
            self.labels.append(
                {
                    "nodeId": node.get("nodeId"),
                    "path": list(path_tuple),
                    "name": node.get("name"),
                    "text": text,
                }
            )
        self.labels.sort(key=lambda item: tuple(item["path"]))
        if not self.labels:
            raise ValueError(f"分类树快照没有可用的叶子节点：space={space}")
        self.label_texts = [item["text"] for item in self.labels]

    def is_valid(self, path: list[str]) -> bool:
        return tuple(path) in self.paths
