"""OP-17 单测与端到端：确定性选样、配额、无重复、续跑、Parquet 与 manifest 对账。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from op17_env import CORE, OP02_EVIDENCE, OP05_EVIDENCE, OP15_EVIDENCE, REPO_ROOT, latest_run

cfg = CORE.load_config()
source = CORE.source_util
select = CORE.select_util


def _record(record_id: str, source_alias: str = "web_text", modal: str = "text") -> dict:
    return {
        "record_id": record_id,
        "modal": modal,
        "source": source_alias,
        "text": f"text-{record_id}",
        "metadata": {"format": "txt", "sizeBytes": 10},
        "quality": {"completeness": 1.0, "decodable": True},
        "partitions": {"modal": modal, "source": source_alias, "dt": "2026-11-17"},
        "hashes": {"md5": None, "sha256": None},
    }


def _label(record_id: str, path: list[str], confidence: float = 0.9, unclassified: bool = False) -> dict:
    return {
        "record_id": record_id,
        "unclassified": unclassified,
        "labels": [] if unclassified else [
            {"path": path, "confidence": confidence, "modelVersion": "m1", "treeVersion": "t1"}
        ],
        "reasonCode": "UNCLASSIFIED" if unclassified else None,
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    input_dir = tmp_path / "input"
    plan_dir = input_dir / "plan"
    plan_dir.mkdir(parents=True)
    plan_rows = [
        {"label": "A/a1/x", "level1": "A", "level2": "A/a1", "feedCount": 2, "bySource": {"web_text": {"effectiveCount": 2}}},
        {"label": "B/b1/y", "level1": "B", "level2": "B/b1", "feedCount": 2, "bySource": {"books": {"effectiveCount": 2}}},
        {"label": "C/c1/z", "level1": "C", "level2": "C/c1", "feedCount": 1, "bySource": {"wiki": {"effectiveCount": 1}}},
    ]
    (plan_dir / "plan.json").write_text(
        json.dumps({"rows": plan_rows, "normalization": {"targetTotal": 5}}, ensure_ascii=False),
        encoding="utf-8",
    )
    records = [
        _record("r1", "web_text"), _record("r2", "web_text"), _record("r3", "books"),
        _record("r4", "books"), _record("r5", "wiki"), _record("r6", "web_text"),
        _record("r7", "web_text"), _record("r8", "web_text"),
    ]
    records_path = input_dir / "records.jsonl"
    records_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    labels = [
        _label("r1", ["A", "a1", "x"], 0.9),
        _label("r2", ["A", "a1", "x"], 0.8),
        _label("r3", ["B", "b1", "y"], 0.9),
        _label("r4", ["B", "b1", "y"], 0.8),
        _label("r5", ["C", "c1", "z"], 0.9),
        _label("r6", ["A", "a1", "x"], 0.7),
        _label("r7", ["D", "d1", "w"], 0.9),
        _label("r8", ["A", "a1", "x"], 0.0, unclassified=True),
    ]
    labels_path = input_dir / "labels.jsonl"
    labels_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in labels) + "\n", encoding="utf-8")
    return plan_dir, records_path, labels_path


def test_selection_quota_and_no_duplicates(tmp_path: Path):
    plan_dir, records_path, labels_path = _fixture(tmp_path)
    plan_rows, target_total, _ = source.load_plan(str(plan_dir))
    records, _ = source.load_records(records_path, 100)
    labels, _ = source.load_labels(labels_path, 100)
    index = source.build_index(plan_rows, records, labels)
    checkpoint = tmp_path / "checkpoint.json"
    selected, quotas, _, resumed = select.select(plan_rows, index["assigned"], 42, "p1", checkpoint)
    assert resumed is False
    assert target_total == 5
    assert len(selected) == 5
    assert len({item["record_id"] for item in selected}) == 5
    by_label = {item["label"]: item for item in quotas}
    assert by_label["A/a1/x"]["selected"] == 2
    assert by_label["B/b1/y"]["selected"] == 2
    assert by_label["C/c1/z"]["selected"] == 1
    assert by_label["A/a1/x"]["status"] == "ok"
    skipped = {item["id"]: item["reasonCode"] for item in index["skipped"]}
    assert skipped["r7"] == "LABEL_NOT_IN_PLAN"
    assert skipped["r8"] == "UNCLASSIFIED"
    assert by_label["A/a1/x"]["recordIds"] == sorted(
        by_label["A/a1/x"]["recordIds"],
        key=lambda record_id: (hashlib.sha256(f"42|{record_id}".encode()).hexdigest(), record_id),
    )


def test_selection_resume(tmp_path: Path):
    plan_dir, records_path, labels_path = _fixture(tmp_path)
    plan_rows, _, _ = source.load_plan(str(plan_dir))
    records, _ = source.load_records(records_path, 100)
    labels, _ = source.load_labels(labels_path, 100)
    index = source.build_index(plan_rows, records, labels)
    checkpoint = tmp_path / "checkpoint.json"
    first, _, payload, _ = select.select(plan_rows, index["assigned"], 42, "p1", checkpoint)
    # 模拟在 A 完成后中断：只保留 A 的 checkpoint，删除 B/C 的选中记录。
    a_label = "A/a1/x"
    a_ids = payload["perLabel"][a_label]["recordIds"]
    partial = {
        "version": "0.1.0",
        "paramsHash": "p1",
        "seed": 42,
        "completedLabels": [a_label],
        "perLabel": {a_label: payload["perLabel"][a_label]},
        "selectedIds": list(a_ids),
    }
    checkpoint.write_text(json.dumps(partial, ensure_ascii=False), encoding="utf-8")
    second, _, _, resumed = select.select(plan_rows, index["assigned"], 42, "p1", checkpoint)
    assert resumed is True
    second_ids = {item["record_id"] for item in second}
    assert set(a_ids) <= second_ids
    assert len(second_ids) == len(first)
    assert second_ids == {item["record_id"] for item in first}


def test_core_packages_parquet_and_manifest(tmp_path: Path, monkeypatch):
    plan_dir, records_path, labels_path = _fixture(tmp_path)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path / "input"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    result = CORE.run(
        str(plan_dir),
        {"records_path": str(records_path), "labels_path": str(labels_path)},
        42,
        str(tmp_path / "out"),
    )
    assert result["sampleCount"] == 5
    assert result["metrics"]["duplicateRecords"] == 0
    assert result["metrics"]["dataset"]["rows"] == 5
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["runId"] == result["metrics"]["runId"]
    assert sum(item["rows"] for item in manifest["dataset"]["files"]) == 5
    for item in manifest["dataset"]["files"]:
        path = tmp_path / "out" / item["path"]
        assert path.is_file()
        assert path.stat().st_size == item["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        table = pq.read_table(path)
        assert table.num_rows == item["rows"]
    assert (tmp_path / "out" / "dataset").is_dir()


def test_core_deterministic(tmp_path: Path, monkeypatch):
    plan_dir, records_path, labels_path = _fixture(tmp_path)
    monkeypatch.setenv("INPUT_DIR", str(tmp_path / "input"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    CORE.run(str(plan_dir), {"records_path": str(records_path), "labels_path": str(labels_path)}, 42, str(tmp_path / "a"))
    CORE.run(str(plan_dir), {"records_path": str(records_path), "labels_path": str(labels_path)}, 42, str(tmp_path / "b"))
    left = (tmp_path / "a" / "selected.jsonl").read_bytes()
    right = (tmp_path / "b" / "selected.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_real_batch(tmp_path: Path, monkeypatch):
    op15 = latest_run(OP15_EVIDENCE)
    op02 = latest_run(OP02_EVIDENCE)
    op05 = latest_run(OP05_EVIDENCE)
    if not op15 or not op02 or not op05:
        pytest.skip("缺少 OP-15/OP-02/OP-05 证据目录")
    if not any(row.get("bySource") for row in json.loads((op15 / "plan.json").read_text(encoding="utf-8"))["rows"]):
        pytest.skip("OP-15 证据缺少 bySource")
    monkeypatch.setenv("INPUT_DIR", str(REPO_ROOT / "operator"))
    monkeypatch.setenv("OUTPUT_DIR", str(REPO_ROOT / "operator"))
    result = CORE.run(
        str(op15),
        {"records_path": str(op02), "labels_path": str(op05)},
        42,
        str(tmp_path / "real"),
    )
    assert result["sampleCount"] > 0
    assert result["metrics"]["duplicateRecords"] == 0
    assert result["metrics"]["dataset"]["rows"] == result["sampleCount"]
