"""OP-05 端到端测试：文本/图像/音频/视频四模态、路径合法、幂等、缺失媒体。"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from op05_env import CORE, OP02_EVIDENCE

pytestmark = pytest.mark.skipif(
    not OP02_EVIDENCE.is_dir(), reason="缺少 S1 OP-02 证据目录"
)


def _record(record_id: str, text: str | None, modal: str = "text") -> dict:
    text = text or ""
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "record_id": record_id,
        "modal": modal,
        "source": "web_text",
        "text": text if modal == "text" else None,
        "metadata": {
            "format": "txt" if modal == "text" else modal,
            "sizeBytes": len(text.encode()),
            "sha256": sha,
            "extra": {},
        },
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": not text.strip()},
        "partitions": {"modal": modal, "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": "0" * 32, "sha256": sha, "simhash": None, "phash": None},
    }


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
        encoding="utf-8",
    )


def test_text_labeling_and_idempotent(tmp_path):
    records = [
        _record("r_ml", "机器学习是人工智能的一个分支，研究从数据中学习规律。"),
        _record("r_fin", "股票市场与宏观经济政策影响投资者预期。"),
        _record("r_empty", ""),
    ]
    source = tmp_path / "records.jsonl"
    _write(source, records)
    first = CORE.run(str(source), params={}, seed=42, output_dir=str(tmp_path / "a"))
    second = CORE.run(str(source), params={}, seed=42, output_dir=str(tmp_path / "b"))
    assert first["sampleCount"] == 3
    assert first["successCount"] + first["failedCount"] == 3
    assert first["treeVersion"] == "taxonomy-1013-pending"
    assert first["metrics"]["labelSpaceSize"] == 279
    assert "annotation" not in first["metrics"]

    rows = [
        json.loads(line)
        for line in (tmp_path / "a" / "result.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    empty = next(row for row in rows if row["record_id"] == "r_empty")
    assert empty["reasonCode"] == "UNCLASSIFIED_EMPTY_TEXT"
    for row in rows:
        for label in row.get("labels", []):
            assert len(label["path"]) == 3
            assert 0 <= label["confidence"] <= 1
            assert label["treeVersion"] == "taxonomy-1013-pending"

    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_multimodal_labeling_with_real_media(tmp_path):
    all_records = [
        json.loads(line)
        for line in (OP02_EVIDENCE / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    selected = [record for record in all_records if record["modal"] != "text"]
    records = tmp_path / "records.jsonl"
    _write(records, selected)
    shutil.copytree(OP02_EVIDENCE / "standard", tmp_path / "standard")
    shutil.copytree(OP02_EVIDENCE / "index", tmp_path / "index")

    result = CORE.run(str(records), params={}, seed=42, output_dir=str(tmp_path / "out"))
    rows = [
        json.loads(line)
        for line in (tmp_path / "out" / "result.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {row["modal"] for row in rows} >= {"image", "audio", "video"}
    labeled = [row for row in rows if row["labels"]]
    assert labeled, "至少应有一条媒体记录成功打标"
    for row in labeled:
        assert row["labels"][0]["evidence"]["source"] in {"ocr", "asr", "video_fusion"}
    metrics = result["metrics"]
    assert metrics["toolVersions"]["rapidocr"]
    assert metrics["toolVersions"]["funasr"]
    assert metrics["pathLegalRate"] == 1.0


def test_missing_standard_media(tmp_path):
    record = _record("r_missing", None, modal="image")
    source = tmp_path / "records.jsonl"
    _write(source, [record])
    result = CORE.run(str(source), params={}, seed=42, output_dir=str(tmp_path / "out"))
    assert result["failedCount"] == 1
    assert result["failedSamples"][0]["reasonCode"] == "STANDARD_MEDIA_MISSING"
