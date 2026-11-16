"""标签治理规则：树校验、最近节点、冲突对、PII 扫描。"""

from __future__ import annotations

import re
from typing import Any

from .common import read_json, resolve_operator_path


class Trees:
    def __init__(self, cfg: dict[str, Any]) -> None:
        snapshot = read_json(resolve_operator_path(cfg["tree"]["relativePath"]))
        self.tree_version = str(snapshot["treeVersion"])
        self.paths_by_space: dict[str, set[tuple[str, ...]]] = {}
        for space in cfg["tree"]["spaces"]:
            nodes = snapshot["trees"][space]["nodes"]
            max_depth = max(int(node.get("depth", 0)) for node in nodes) if nodes else 0
            self.paths_by_space[space] = {
                tuple(node["path"])
                for node in nodes
                if bool(node.get("leaf")) or int(node.get("depth", 0)) >= max_depth
            }
        self.all_paths: set[tuple[str, ...]] = set().union(*self.paths_by_space.values())

    def space_of(self, path: list[str]) -> str | None:
        target = tuple(path)
        for space, paths in self.paths_by_space.items():
            if target in paths:
                return space
        return None

    def is_valid(self, path: list[str]) -> bool:
        return tuple(path) in self.all_paths

    def nearest(self, path: list[str], max_distance: int) -> dict[str, Any] | None:
        target = " > ".join(path)
        best = None
        for candidate in sorted(self.all_paths):
            distance = _levenshtein(target, " > ".join(candidate))
            if best is None or distance < best[0]:
                best = (distance, candidate)
        if best is None or best[0] > max_distance:
            return None
        return {"path": list(best[1]), "distance": best[0]}


def extract_labels(row: dict[str, Any]) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for key in ("labels", "domainLabels", "abilityLabels"):
        value = row.get(key)
        if not isinstance(value, list):
            continue
        for label in value:
            if isinstance(label, dict) and isinstance(label.get("path"), list):
                labels.append({**label, "sourceKey": key})
    return labels


def detect_conflicts(
    record_id: str, labels: list[dict[str, Any]], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    min_confidence = float(cfg["rules"]["minConfidence"])
    conflicts: list[dict[str, Any]] = []
    seen: dict[tuple[str, ...], int] = {}
    for label in labels:
        key = tuple(label["path"])
        seen[key] = seen.get(key, 0) + 1
    for path, count in seen.items():
        if count > 1:
            conflicts.append(
                {
                    "recordId": record_id,
                    "type": "DUPLICATE_PATH",
                    "paths": [list(path), list(path)],
                    "detail": f"同一记录重复出现 {count} 次",
                }
            )
    for index, left in enumerate(labels):
        for right in labels[index + 1 :]:
            if tuple(left["path"]) == tuple(right["path"]):
                continue
            if left["path"][0] == right["path"][0]:
                continue
            if (
                float(left.get("confidence") or 0) >= min_confidence
                and float(right.get("confidence") or 0) >= min_confidence
            ):
                conflicts.append(
                    {
                        "recordId": record_id,
                        "type": "CROSS_DOMAIN_CONFLICT",
                        "paths": [left["path"], right["path"]],
                        "detail": "同一记录命中不同一级类目且均高于置信度阈值",
                    }
                )
    return conflicts


def label_issue(
    label: dict[str, Any], trees: Trees, cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not trees.is_valid(label["path"]):
        suggestion = trees.nearest(
            label["path"], int(cfg["rules"]["nearestNodeMaxDistance"])
        )
        issues.append(
            {
                "type": "ILLEGAL_PATH",
                "path": label["path"],
                "suggestion": suggestion,
                "detail": f"路径不在 {trees.tree_version} 中",
            }
        )
    confidence = float(label.get("confidence") or 0)
    if confidence < float(cfg["rules"]["minConfidence"]):
        issues.append(
            {
                "type": "LOW_CONFIDENCE",
                "path": label["path"],
                "value": confidence,
                "threshold": float(cfg["rules"]["minConfidence"]),
            }
        )
    return issues


def pii_scan(text: str | None, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if not text or not cfg["pii"].get("enabled", True):
        return []
    hits: list[dict[str, Any]] = []
    for name, pattern in cfg["pii"]["patterns"].items():
        for match in re.finditer(pattern, text):
            value = match.group(0)
            hits.append(
                {
                    "type": name,
                    "value": _redact(value),
                    "position": match.start(),
                }
            )
    return hits


def _redact(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, start=1):
        current = [i]
        for j, char_right in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_left != char_right),
                )
            )
        previous = current
    return previous[-1]
