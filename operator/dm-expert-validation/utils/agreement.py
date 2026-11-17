"""专家一致性：Cohen's Kappa、Krippendorff's Alpha、共识、逐标签 P/R/F1 与争议。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_expert(path: Path | None, min_raters: int) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    """返回 ``{record_id: {expertId: label}}``。"""

    ratings: dict[str, dict[str, str]] = defaultdict(dict)
    failures: list[dict[str, Any]] = []
    if path is None or not path.is_file():
        return {}, failures
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append({"id": f"line:{number}", "reasonCode": "EXPERT_JSON_INVALID", "detail": str(exc)})
                continue
            record_id = str(row.get("record_id") or "")
            expert_id = str(row.get("expertId") or row.get("expert") or "")
            label = row.get("label") or row.get("path")
            if isinstance(label, list):
                label = "/".join(str(item) for item in label)
            if not record_id or not expert_id or not label:
                failures.append({"id": record_id or f"line:{number}", "reasonCode": "EXPERT_FIELD_MISSING"})
                continue
            ratings[record_id][expert_id] = str(label)
    return dict(ratings), failures


def _cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if len(pairs) < 2:
        return None
    categories = sorted({value for pair in pairs for value in pair})
    index = {value: position for position, value in enumerate(categories)}
    matrix = [[0] * len(categories) for _ in categories]
    for left, right in pairs:
        matrix[index[left]][index[right]] += 1
    total = len(pairs)
    observed = sum(matrix[i][i] for i in range(len(categories))) / total
    row = [sum(matrix[i]) for i in range(len(categories))]
    column = [sum(matrix[i][j] for i in range(len(categories))) for j in range(len(categories))]
    expected = sum(row[i] * column[i] for i in range(len(categories))) / (total * total)
    if abs(1 - expected) < 1e-12:
        return None
    return (observed - expected) / (1 - expected)


def pairwise_kappa(ratings: dict[str, dict[str, str]]) -> dict[str, Any]:
    experts = sorted({expert for item in ratings.values() for expert in item})
    pairs = []
    for left_index, left in enumerate(experts):
        for right in experts[left_index + 1 :]:
            common = [
                (values[left], values[right])
                for values in ratings.values()
                if left in values and right in values
            ]
            kappa = _cohen_kappa(common)
            pairs.append({"experts": [left, right], "items": len(common), "kappa": round(kappa, 10) if kappa is not None else None})
    values = [item["kappa"] for item in pairs if item["kappa"] is not None]
    return {
        "experts": experts,
        "pairs": pairs,
        "meanKappa": round(sum(values) / len(values), 10) if values else None,
    }


def krippendorff_alpha(ratings: dict[str, dict[str, str]]) -> float | None:
    items = [list(values.values()) for values in ratings.values() if len(values) >= 2]
    if not items:
        return None
    total_ratings = sum(len(item) for item in items)
    if total_ratings < 2:
        return None
    categories = sorted({label for item in items for label in item})
    counts_per_item = [Counter(item) for item in items]
    observed = 0.0
    for item, counts in zip(items, counts_per_item):
        m = len(item)
        if m < 2:
            continue
        observed += sum(count * (m - count) for count in counts.values()) / (m - 1)
    observed /= total_ratings
    totals = Counter()
    for counts in counts_per_item:
        totals.update(counts)
    expected = sum(count * (total_ratings - count) for count in totals.values()) / (total_ratings * (total_ratings - 1))
    if expected <= 1e-12:
        return None
    return 1 - observed / expected


def consensus(ratings: dict[str, dict[str, str]]) -> dict[str, str]:
    result = {}
    for record_id, values in ratings.items():
        counts = Counter(values.values())
        top = counts.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            result[record_id] = "DISPUTED"
        else:
            result[record_id] = top[0][0]
    return result


def evaluate(
    sampled: list[dict[str, Any]],
    ratings: dict[str, dict[str, str]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    min_raters = int(cfg["agreement"]["minRaters"])
    usable = {
        record_id: values
        for record_id, values in ratings.items()
        if len(values) >= min_raters
    }
    if not usable:
        return {
            "status": "blocked",
            "blockedReason": "EXPERT_ANNOTATIONS_REQUIRED",
            "message": "未提供至少 2 位专家对同一样本的标注（H-05），不计算 Kappa/Alpha。",
            "kappa": None,
            "alpha": None,
            "consensus": None,
            "perLabel": None,
            "disputes": [],
            "sampledWithAnnotations": 0,
        }
    kappa = pairwise_kappa(usable)
    alpha = krippendorff_alpha(usable)
    consensus_labels = consensus(usable)
    sampled_by_id = {item["record_id"]: item for item in sampled}
    auto = {
        record_id: sampled_by_id[record_id]["label"]
        for record_id in usable
        if record_id in sampled_by_id
    }
    compared = [
        (record_id, auto[record_id], consensus_labels[record_id])
        for record_id in auto
        if consensus_labels[record_id] != "DISPUTED"
    ]
    accuracy = (
        sum(1 for _, predicted, gold in compared if predicted == gold) / len(compared)
        if compared
        else None
    )
    labels = sorted({gold for _, _, gold in compared})
    per_label = {}
    f1_values = []
    for label in labels:
        tp = sum(1 for _, predicted, gold in compared if predicted == label and gold == label)
        fp = sum(1 for _, predicted, gold in compared if predicted == label and gold != label)
        fn = sum(1 for _, predicted, gold in compared if predicted != label and gold == label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"support": tp + fn, "precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6)}
        f1_values.append(f1)
    disputes = []
    for record_id, values in sorted(usable.items(), key=lambda item: item[0]):
        distinct = set(values.values())
        if len(distinct) <= 1:
            continue
        disputes.append(
            {
                "record_id": record_id,
                "autoLabel": auto.get(record_id),
                "consensus": consensus_labels.get(record_id),
                "ratings": sorted(values.items()),
                "distinctLabels": sorted(distinct),
            }
        )
    disputes.sort(key=lambda item: (-len(item["distinctLabels"]), -len(item["ratings"]), item["record_id"]))
    return {
        "status": "ok",
        "kappa": kappa,
        "alpha": round(alpha, 10) if alpha is not None else None,
        "consensus": {
            "method": cfg["agreement"]["consensus"],
            "labels": {record_id: consensus_labels[record_id] for record_id in sorted(consensus_labels)},
            "disputedCount": sum(1 for value in consensus_labels.values() if value == "DISPUTED"),
        },
        "accuracyVsConsensus": round(accuracy, 10) if accuracy is not None else None,
        "macroF1VsConsensus": round(sum(f1_values) / len(f1_values), 10) if f1_values else None,
        "perLabel": per_label,
        "disputes": disputes[: int(cfg["agreement"]["maxDisputes"])],
        "disputeCount": len(disputes),
        "sampledWithAnnotations": len(auto),
        "thresholds": {"kappaGood": float(cfg["agreement"]["kappaGood"]), "alphaGood": float(cfg["agreement"]["alphaGood"])},
        "definition": (
            "Kappa 为专家两两 Cohen's Kappa 的均值；Alpha 为 Krippendorff 名义 alpha；"
            "共识取多数票，平票记 DISPUTED；accuracy/F1 以共识为金标准、对比自动标签。"
        ),
    }
