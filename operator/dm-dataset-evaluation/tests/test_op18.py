"""OP-18 单测：抽样、真值指标、代理指标、合规、综合分与版本一致性。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from op18_env import CORE, OP17_EVIDENCE, latest_run

cfg = CORE.load_config()

LABEL_A = "新闻与资讯/科技新闻/产品发布与行业动态"
LABEL_B = "知识与参考/百科词条/百科条目"
SCHEMA = pa.schema(
    [
        ("record_id", pa.string()),
        ("label", pa.string()),
        ("level1", pa.string()),
        ("level2", pa.string()),
        ("confidence", pa.float64()),
        ("selection_rank", pa.int64()),
        ("modal", pa.string()),
        ("source", pa.string()),
        ("dt", pa.string()),
        ("text", pa.string()),
        ("metadata_json", pa.string()),
        ("quality_json", pa.string()),
        ("partitions_json", pa.string()),
        ("hashes_json", pa.string()),
    ]
)


def _build_run(tmp_path: Path, count: int = 10, wrong: int = 0, truth: bool = True) -> Path:
    run_dir = tmp_path / "op17"
    dataset_dir = run_dir / "dataset" / "modal=text" / "source=web_text" / "dt=2026-11-17"
    dataset_dir.mkdir(parents=True)
    rows = []
    truth_rows = []
    for index in range(count):
        label = LABEL_A if index % 2 == 0 else LABEL_B
        truth_label = label
        if index < wrong:
            truth_label = LABEL_B if label == LABEL_A else LABEL_A
        rows.append(
            {
                "record_id": f"r{index}",
                "label": label,
                "level1": label.split("/")[0],
                "level2": "/".join(label.split("/")[:2]),
                "confidence": 0.8,
                "selection_rank": index,
                "modal": "text",
                "source": "web_text",
                "dt": "2026-11-17",
                "text": "包含敏感词的内容" if index == 0 else f"text-{index}",
                "metadata_json": "{}",
                "quality_json": json.dumps({"completeness": 1.0}),
                "partitions_json": json.dumps({"modal": "text", "source": "web_text", "dt": "2026-11-17"}),
                "hashes_json": json.dumps({"sha256": f"hash{index}", "md5": None}),
            }
        )
        truth_rows.append({"record_id": f"r{index}", "path": truth_label.split("/")})
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    path = dataset_dir / "part-00000.parquet"
    pq.write_table(table, path)
    manifest = {
        "runId": "op17run",
        "operatorVersion": "0.1.0",
        "modelVersion": "m1",
        "treeVersion": "taxonomy-1013-pending",
        "sampleCount": count,
        "dataset": {
            "rows": count,
            "files": [{"path": path.relative_to(run_dir).as_posix(), "rows": count}],
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    if truth:
        (tmp_path / "truth.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in truth_rows) + "\n", encoding="utf-8"
        )
    return run_dir


def _run(tmp_path: Path, monkeypatch, run_dir: Path, params: dict | None = None) -> dict:
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    return CORE.run(str(run_dir), params or {}, 42, str(tmp_path / "out"))


def test_truth_metrics(tmp_path: Path, monkeypatch):
    run_dir = _build_run(tmp_path, count=10, wrong=2)
    result = _run(
        tmp_path,
        monkeypatch,
        run_dir,
        {"ratio": 1.0, "truth_path": str(tmp_path / "truth.jsonl")},
    )
    metrics = result["metrics"]
    assert metrics["truth"]["status"] == "ok"
    assert metrics["truth"]["accuracy"] == pytest.approx(0.8)
    assert metrics["truth"]["macroF1"] is not None
    assert metrics["sampleSize"] == 10
    assert result["failedCount"] == 0
    assert metrics["proxy"]["pathLegalityRate"] == 1.0
    wrong_path = tmp_path / "out" / "wrong_labels.jsonl"
    assert len(wrong_path.read_text(encoding="utf-8").splitlines()) == 2
    assert (tmp_path / "out" / "confusion.json").is_file()


def test_no_truth_is_null(tmp_path: Path, monkeypatch):
    run_dir = _build_run(tmp_path, count=10, truth=False)
    result = _run(tmp_path, monkeypatch, run_dir, {"ratio": 1.0})
    metrics = result["metrics"]
    assert metrics["truth"]["status"] == "unavailable"
    assert metrics["truth"]["blockedReason"] == "TRUTH_REQUIRED"
    assert metrics["truth"]["accuracy"] is None
    assert metrics["truth"]["macroF1"] is None
    assert metrics["proxy"]["proxy"] is True
    assert metrics["proxy"]["pathLegalityRate"] == 1.0
    assert metrics["score"]["score"] is not None


def test_compliance_missing_and_provided(tmp_path: Path, monkeypatch):
    run_dir = _build_run(tmp_path, count=10)
    result = _run(tmp_path, monkeypatch, run_dir, {"ratio": 1.0})
    assert result["metrics"]["compliance"]["status"] == "unavailable"
    assert result["metrics"]["compliance"]["hitRate"] is None

    terms = tmp_path / "terms.json"
    terms.write_text(json.dumps(["敏感词"], ensure_ascii=False), encoding="utf-8")
    result = _run(
        tmp_path,
        monkeypatch,
        run_dir,
        {"ratio": 1.0, "compliance_terms_path": str(terms)},
    )
    assert result["metrics"]["compliance"]["status"] == "ok"
    assert result["metrics"]["compliance"]["hitCount"] == 1
    assert result["metrics"]["compliance"]["hitRate"] == pytest.approx(0.1)


def test_composite_score_formula(tmp_path: Path, monkeypatch):
    run_dir = _build_run(tmp_path, count=10, wrong=2)
    result = _run(
        tmp_path,
        monkeypatch,
        run_dir,
        {"ratio": 1.0, "truth_path": str(tmp_path / "truth.jsonl")},
    )
    score = result["metrics"]["score"]
    # 可用：accuracy 0.8 (0.4)、path 1.0 (0.2)、completeness 1.0 (0.2)；compliance 不可用。
    expected = (0.4 * 0.8 + 0.2 * 1.0 + 0.2 * 1.0) / 0.8
    assert score["score"] == pytest.approx(expected)
    assert score["components"]["compliance"]["available"] is False


def test_sampling_deterministic(tmp_path: Path, monkeypatch):
    run_dir = _build_run(tmp_path, count=100)
    first = _run(tmp_path, monkeypatch, run_dir, {"ratio": 0.1})
    second = CORE.run(str(run_dir), {"ratio": 0.1}, 42, str(tmp_path / "out2"))
    left = (tmp_path / "out" / "sampled.jsonl").read_bytes()
    right = (tmp_path / "out2" / "sampled.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()
    assert first["metrics"]["sampleSize"] == second["metrics"]["sampleSize"] == 10


def test_version_mismatch_blocks(tmp_path: Path, monkeypatch):
    run_dir = _build_run(tmp_path, count=10)
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()
    (labels_dir / "manifest.json").write_text(
        json.dumps({"modelVersion": "other", "treeVersion": "taxonomy-1013-pending"}),
        encoding="utf-8",
    )
    result = _run(
        tmp_path,
        monkeypatch,
        run_dir,
        {"ratio": 1.0, "labels_path": str(labels_dir)},
    )
    assert result["blockedReason"] == "MODEL_TREE_MISMATCH"


def test_real_batch(tmp_path: Path, monkeypatch):
    run_dir = latest_run(OP17_EVIDENCE)
    if run_dir is None or not (run_dir / "manifest.json").is_file():
        pytest.skip("缺少 OP-17 证据目录")
    monkeypatch.setenv("INPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    result = CORE.run(str(run_dir), {}, 42, str(tmp_path / "real"))
    assert result["sampleCount"] > 0
    assert result["metrics"]["proxy"]["pathLegalityRate"] == 1.0
