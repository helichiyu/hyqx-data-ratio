"""读取 OP-15 配方、OP-02 记录与 OP-05 标签，构建「记录→单一标签」索引。

每条记录只归入一个标签（confidence 最高，平票按路径升序），保证成品无重复；
无标签、标签不在配方、记录缺失的样本进入失败/跳过清单，不静默丢弃。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def locate_file(raw: str | Path, preferred_names: tuple[str, ...]) -> Path:
    """目录取首选文件，文件原样返回。"""

    path = Path(raw).resolve()
    if path.is_file():
        return path
    for name in preferred_names:
        candidate = path / name
        if candidate.is_file():
            return candidate
    matches = sorted(path.glob("*.jsonl"))
    preferred = [item for item in matches if "record" in item.name.lower()]
    if preferred:
        return preferred[0]
    if matches:
        return matches[0]
    raise FileNotFoundError(f"目录中没有可读文件：{path}")


def load_plan(input_path: str) -> tuple[list[dict[str, Any]], int, Path]:
    path = Path(input_path).resolve()
    if path.is_dir():
        candidate = path / "plan.json"
        if not candidate.is_file():
            raise FileNotFoundError(f"OP-15 运行目录缺少 plan.json：{path}")
        path = candidate
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"plan.json 缺少非空 rows：{path}")
    target_total = int((payload.get("normalization") or {}).get("targetTotal") or 0)
    return [dict(row) for row in rows], target_total, path


def load_records(records_path: Path, max_records: int) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    with records_path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if len(records) >= max_records:
                failures.append({"id": f"line:{number}", "reasonCode": "RECORD_LIMIT_EXCEEDED"})
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append({"id": f"line:{number}", "reasonCode": "RECORD_JSON_INVALID", "detail": str(exc)})
                continue
            record_id = str(record.get("record_id") or "")
            if not record_id:
                failures.append({"id": f"line:{number}", "reasonCode": "RECORD_ID_MISSING"})
                continue
            if record_id in records:
                failures.append({"id": record_id, "reasonCode": "RECORD_ID_DUPLICATE"})
                continue
            records[record_id] = record
    return records, failures


def _top_label(row: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    for label in row.get("labels") or []:
        if not isinstance(label, dict):
            continue
        path = label.get("path")
        if not isinstance(path, list) or not path:
            continue
        path_text = "/".join(str(item) for item in path)
        candidates.append((float(label.get("confidence") or 0.0), path_text, [str(item) for item in path], label))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    confidence, path_text, path, label = candidates[0]
    return {
        "label": path_text,
        "path": path,
        "confidence": confidence,
        "modelVersion": label.get("modelVersion"),
        "treeVersion": label.get("treeVersion"),
    }


def load_labels(labels_path: Path, max_records: int) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    labels: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    with labels_path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if len(labels) >= max_records:
                failures.append({"id": f"line:{number}", "reasonCode": "LABEL_LIMIT_EXCEEDED"})
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append({"id": f"line:{number}", "reasonCode": "LABEL_JSON_INVALID", "detail": str(exc)})
                continue
            record_id = str(row.get("record_id") or "")
            if not record_id:
                failures.append({"id": f"line:{number}", "reasonCode": "LABEL_RECORD_ID_MISSING"})
                continue
            if row.get("unclassified") or not row.get("labels"):
                labels[record_id] = {"label": None, "reasonCode": row.get("reasonCode") or "UNCLASSIFIED"}
                continue
            top = _top_label(row)
            if top is None:
                labels[record_id] = {"label": None, "reasonCode": "LABEL_PATH_INVALID"}
                continue
            labels[record_id] = top
    return labels, failures


def build_index(
    plan_rows: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    labels: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    plan_labels = {str(row["label"]) for row in plan_rows}
    assigned: dict[str, list[str]] = {label: [] for label in plan_labels}
    record_labels: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    model_versions: Counter[str] = Counter()
    tree_versions: Counter[str] = Counter()

    for record_id, record in records.items():
        label_info = labels.get(record_id)
        if label_info is None:
            skipped.append({"id": record_id, "reasonCode": "LABEL_MISSING"})
            continue
        if not label_info.get("label"):
            skipped.append(
                {
                    "id": record_id,
                    "reasonCode": label_info.get("reasonCode") or "UNCLASSIFIED",
                }
            )
            continue
        label = str(label_info["label"])
        if label not in assigned:
            skipped.append({"id": record_id, "reasonCode": "LABEL_NOT_IN_PLAN", "detail": label})
            continue
        path = label_info["path"]
        record_labels[record_id] = {
            "label": label,
            "level1": path[0],
            "level2": "/".join(path[:2]),
            "confidence": float(label_info.get("confidence") or 0.0),
            "path": path,
        }
        assigned[label].append(record_id)
        if label_info.get("modelVersion"):
            model_versions[str(label_info["modelVersion"])] += 1
        if label_info.get("treeVersion"):
            tree_versions[str(label_info["treeVersion"])] += 1

    return {
        "assigned": assigned,
        "recordLabels": record_labels,
        "skipped": skipped,
        "modelVersions": [item for item, _ in model_versions.most_common()],
        "treeVersions": [item for item, _ in tree_versions.most_common()],
    }
