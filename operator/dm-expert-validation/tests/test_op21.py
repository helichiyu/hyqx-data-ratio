"""OP-21 单测：抽样、高风险必选、Kappa/Alpha、无标注 blocked。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from op21_env import CORE

cfg = CORE.load_config()
agreement = CORE.agreement_util


def _objects(tmp_path: Path, count: int = 20) -> Path:
    rows = [
        {
            "record_id": f"r{index}",
            "label": "A/a/x" if index % 2 == 0 else "B/b/y",
            "level1": "A" if index % 2 == 0 else "B",
            "modal": "text",
        }
        for index in range(count)
    ]
    path = tmp_path / "objects.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return path


def _risk(tmp_path: Path, ids: list[str]) -> Path:
    path = tmp_path / "risk.jsonl"
    path.write_text(
        "\n".join(json.dumps({"record_id": rid, "riskLevel": "high"}) for rid in ids) + "\n",
        encoding="utf-8",
    )
    return path


def test_sample_and_high_risk(tmp_path: Path, monkeypatch):
    objects = _objects(tmp_path)
    risk = _risk(tmp_path, ["r1", "r3", "r5"])
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(str(objects), {"risk_path": str(risk)}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert metrics["sampling"]["sampled"] >= 3
    sampled = [json.loads(line) for line in (tmp_path / "out" / "sampled.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {"r1", "r3", "r5"} <= {item["record_id"] for item in sampled}
    assert metrics["sampling"]["highRiskTotal"] == 3
    assert metrics["agreement"]["status"] == "blocked"
    assert metrics["agreement"]["blockedReason"] == "EXPERT_ANNOTATIONS_REQUIRED"


def test_sample_deterministic(tmp_path: Path, monkeypatch):
    objects = _objects(tmp_path)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    CORE.run(str(objects), {}, 42, str(tmp_path / "a"))
    CORE.run(str(objects), {}, 42, str(tmp_path / "b"))
    left = (tmp_path / "a" / "sampled.jsonl").read_bytes()
    right = (tmp_path / "b" / "sampled.jsonl").read_bytes()
    assert left == right


def test_cohen_kappa_known():
    pairs = [("x", "x")] * 4 + [("y", "y")] * 4 + [("x", "y"), ("y", "x")]
    value = agreement._cohen_kappa(pairs)
    # Po=0.8; marginals 5/5 -> Pe=0.5; kappa=0.6
    assert value == pytest.approx(0.6)


def test_krippendorff_alpha_all_agree():
    ratings = {"r1": {"e1": "x", "e2": "x"}, "r2": {"e1": "y", "e2": "y"}, "r3": {"e1": "x", "e2": "y"}}
    value = agreement.krippendorff_alpha(ratings)
    assert value is not None
    assert -1.0 <= value <= 1.0


def test_expert_agreement(tmp_path: Path, monkeypatch):
    objects = _objects(tmp_path, count=10)
    expert = tmp_path / "expert.jsonl"
    rows = []
    ratings = {}
    sampled = []
    for index in range(10):
        gold = "A/a/x" if index % 2 == 0 else "B/b/y"
        rows.append({"record_id": f"r{index}", "expertId": "e1", "label": gold})
        rows.append({"record_id": f"r{index}", "expertId": "e2", "label": gold if index != 0 else "B/b/y"})
        ratings[f"r{index}"] = {"e1": gold, "e2": gold if index != 0 else "B/b/y"}
        sampled.append({"record_id": f"r{index}", "label": gold})
    expert.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

    report = agreement.evaluate(sampled, ratings, cfg)
    assert report["status"] == "ok"
    assert report["kappa"]["meanKappa"] is not None
    assert report["alpha"] is not None
    assert report["disputeCount"] >= 1

    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(str(objects), {"expert_path": str(expert)}, 42, str(tmp_path / "out"))
    assert result["metrics"]["agreement"]["status"] == "ok"
    assert (tmp_path / "out" / "disputes.jsonl").is_file()
