"""标签评测与代理指标。

有真值时：精确/前缀准确率、逐模态准确率、宏 F1、混淆矩阵、错标清单；
无真值时：准确率/F1/混淆矩阵标 ``null`` + ``TRUTH_REQUIRED``，只输出路径合法率、
置信度分布、完整率等代理指标（明确 ``proxy=true``），不冒充准确率。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_tree_paths(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    nodes = payload["trees"]["content"]["nodes"]
    return {"/".join(str(item) for item in node["path"]) for node in nodes}


def load_truth(path: Path, max_records: int) -> tuple[dict[str, str], list[dict[str, Any]]]:
    truth: dict[str, str] = {}
    failures: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if len(truth) >= max_records:
                failures.append({"id": f"line:{number}", "reasonCode": "TRUTH_LIMIT_EXCEEDED"})
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append({"id": f"line:{number}", "reasonCode": "TRUTH_JSON_INVALID", "detail": str(exc)})
                continue
            record_id = str(row.get("record_id") or "")
            if not record_id:
                failures.append({"id": f"line:{number}", "reasonCode": "TRUTH_RECORD_ID_MISSING"})
                continue
            label = row.get("path")
            if isinstance(label, list) and label:
                label = "/".join(str(item) for item in label)
            elif isinstance(row.get("label"), str):
                label = row["label"]
            else:
                failures.append({"id": record_id, "reasonCode": "TRUTH_LABEL_MISSING"})
                continue
            truth[record_id] = str(label)
    return truth, failures


def _prefix_match(predicted: str, truth: str) -> bool:
    return predicted == truth or predicted.startswith(truth + "/") or truth.startswith(predicted + "/")


def evaluate_truth(
    sampled: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    truth: dict[str, str],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    evaluated = []
    missing = 0
    for item in sampled:
        record_id = item["record_id"]
        if record_id not in truth:
            missing += 1
            continue
        record = records.get(record_id) or {}
        evaluated.append(
            {
                "record_id": record_id,
                "modal": record.get("modal") or "unknown",
                "predicted": str(record.get("label") or ""),
                "truth": truth[record_id],
            }
        )

    if not evaluated:
        return {
            "status": "unavailable",
            "reasonCode": "TRUTH_RECORDS_MATCHED_NONE",
            "accuracy": None,
            "macroF1": None,
            "confusion": None,
            "wrongLabels": [],
            "missingTruth": missing,
        }

    exact = sum(1 for item in evaluated if item["predicted"] == item["truth"])
    prefix = sum(1 for item in evaluated if _prefix_match(item["predicted"], item["truth"]))
    per_modal: dict[str, dict[str, int]] = defaultdict(lambda: {"evaluated": 0, "exact": 0, "prefix": 0})
    for item in evaluated:
        bucket = per_modal[item["modal"]]
        bucket["evaluated"] += 1
        bucket["exact"] += int(item["predicted"] == item["truth"])
        bucket["prefix"] += int(_prefix_match(item["predicted"], item["truth"]))

    labels = sorted({item["truth"] for item in evaluated})
    per_label = {}
    f1_values = []
    for label in labels:
        tp = sum(1 for item in evaluated if item["predicted"] == label and item["truth"] == label)
        fp = sum(1 for item in evaluated if item["predicted"] == label and item["truth"] != label)
        fn = sum(1 for item in evaluated if item["predicted"] != label and item["truth"] == label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "support": tp + fn,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
        }
        f1_values.append(f1)

    confusion = Counter((item["truth"], item["predicted"]) for item in evaluated)
    top_k = int(cfg["matching"]["confusionTopK"])
    frequency = Counter(item["truth"] for item in evaluated)
    top_labels = [label for label, _ in frequency.most_common(top_k)]
    top_set = set(top_labels)

    def shrink(label: str) -> str:
        return label if label in top_set else "OTHER"

    confusion_matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (truth_label, predicted), count in confusion.items():
        confusion_matrix[shrink(truth_label)][shrink(predicted)] += count

    wrong = [
        item
        for item in evaluated
        if item["predicted"] != item["truth"]
    ][: int(cfg["matching"]["maxWrongLabels"])]
    return {
        "status": "ok",
        "accuracy": round(exact / len(evaluated), 10),
        "prefixAccuracy": round(prefix / len(evaluated), 10),
        "macroF1": round(sum(f1_values) / len(f1_values), 10),
        "evaluated": len(evaluated),
        "missingTruth": missing,
        "perModal": {
            modal: {
                "evaluated": bucket["evaluated"],
                "accuracy": round(bucket["exact"] / bucket["evaluated"], 10),
                "prefixAccuracy": round(bucket["prefix"] / bucket["evaluated"], 10),
            }
            for modal, bucket in sorted(per_modal.items())
        },
        "perLabel": per_label,
        "confusion": {truth_label: dict(predicted) for truth_label, predicted in sorted(confusion_matrix.items())},
        "confusionLabels": top_labels,
        "wrongLabels": wrong,
        "definition": (
            "精确准确率 = 完整路径一致；前缀准确率 = 一方为另一方路径前缀；"
            "宏 F1 = 真值标签集合上单标签 P/R/F1 的宏平均；混淆矩阵取真值频次 TopK，其余归 OTHER。"
        ),
    }


def proxy_metrics(
    sampled: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    legal_paths: set[str],
    low_confidence: float,
) -> dict[str, Any]:
    confidences = []
    legal = 0
    completeness = []
    empty_text = 0
    for item in sampled:
        record = records.get(item["record_id"]) or {}
        label = str(record.get("label") or "")
        legal += int(label in legal_paths)
        confidence = record.get("confidence")
        if isinstance(confidence, (int, float)):
            confidences.append(float(confidence))
        try:
            quality = json.loads(record.get("quality_json") or "{}")
        except json.JSONDecodeError:
            quality = {}
        value = quality.get("completeness")
        if isinstance(value, (int, float)):
            completeness.append(float(value))
        if not record.get("text"):
            empty_text += 1
    count = len(sampled) or 1
    confidences.sort()
    return {
        "proxy": True,
        "pathLegalityRate": round(legal / count, 10),
        "meanConfidence": round(sum(confidences) / len(confidences), 10) if confidences else None,
        "medianConfidence": round(confidences[len(confidences) // 2], 10) if confidences else None,
        "lowConfidenceRate": round(
            sum(1 for value in confidences if value < low_confidence) / len(confidences), 10
        ) if confidences else None,
        "meanCompleteness": round(sum(completeness) / len(completeness), 10) if completeness else None,
        "emptyTextRate": round(empty_text / count, 10),
        "lowConfidenceThreshold": low_confidence,
        "note": "代理指标只反映标签合法性与数据完整性，不等价于人工真值准确率（H-05）。",
    }
