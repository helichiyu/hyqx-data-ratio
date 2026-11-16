"""OP-02 纯函数单测：记录校验、文本归一化、去重、Parquet、索引、关联。"""

from __future__ import annotations

import json

from op02_env import OP2


def _record(record_id: str, text: str, sha: str) -> dict:
    return {
        "record_id": record_id,
        "modal": "text",
        "source": "web_text",
        "text": text,
        "metadata": {"format": "txt", "sizeBytes": len(text.encode()), "sha256": sha},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": not text.strip()},
        "partitions": {"modal": "text", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": "0" * 32, "sha256": sha, "simhash": None, "phash": None},
    }


def test_normalize_text():
    raw = "  第一行\r\n\r\n\r\n\r\n第二行  \x07"
    normalized, stats = OP2.schema.normalize_text(raw)
    assert "\r" not in normalized
    assert "\x07" not in normalized
    assert normalized == "第一行\n\n第二行"
    assert stats["changed"] is True
    assert stats["removedControlChars"] == 1
    assert OP2.schema.normalize_text(None)[0] is None


def test_validate_record():
    valid = _record("r_1", "hello", "a" * 64)
    assert OP2.schema.validate_record(valid) == []
    broken = _record("r_2", "hello", "bad")
    assert OP2.schema.validate_record(broken)


def test_dedup_exact_and_near():
    cfg = OP2.load_config("normalize.json")
    sha = "b" * 64
    records = [
        _record("r_a", "数据配比中心算子开发与验收", sha),
        _record("r_b", "数据配比中心算子开发与验收", sha),
        _record("r_c", "数据配比中心算子开发与验收流程", "c" * 64),
        _record("r_d", "完全不同的另一段内容", "d" * 64),
        _record("r_e", "独立的精确重复样本甲", "e" * 64),
        _record("r_f", "独立的精确重复样本甲", "e" * 64),
    ]
    for record in records:
        record["hashes"]["simhash"] = OP2.simhash64(record["text"])
    base_simhash = records[0]["hashes"]["simhash"]
    records[2]["hashes"]["simhash"] = f"{int(base_simhash, 16) ^ 1:016x}"
    groups, duplicate_of, stats = OP2.dedup.find_duplicates(records, cfg)
    assert stats["exactGroups"] >= 1
    assert duplicate_of["r_b"] == "r_a"
    assert duplicate_of["r_c"] == "r_a"
    assert "r_d" not in duplicate_of
    assert groups


def test_parquet_roundtrip(tmp_path):
    cfg = OP2.load_config("normalize.json")
    rows = [
        {
            "record_id": "r_1",
            "modal": "text",
            "source": "web_text",
            "dt": "2026-11-16",
            "text": "示例文本",
            "text_chars": 4,
            "text_sha256": "a" * 64,
            "format": "txt",
            "size_bytes": 12,
            "md5": "0" * 32,
            "sha256": "a" * 64,
            "simhash": None,
            "phash": None,
            "standard_path": "standard/parquet/x.parquet",
            "duplicate_of": None,
            "quality_json": "{}",
            "metadata_json": "{}",
        }
    ]
    path = tmp_path / "part.parquet"
    OP2.writer.write_parquet(
        rows, path, row_group_size=100, compression=cfg["partition"]["compression"]
    )
    assert OP2.writer.read_parquet_rows(path)[0]["text"] == "示例文本"


def test_associations_and_partition_stats():
    records = [
        _record("r_text", "文本", "a" * 64),
        {
            **_record("r_video", "", "b" * 64),
            "modal": "video",
            "text": None,
            "partitions": {"modal": "video", "source": "web_text", "dt": "2026-11-16"},
            "metadata": {"format": "mp4", "sizeBytes": 10, "sha256": "b" * 64,
                         "extra": {"file": "batch.zip/v.mp4"}},
            "hashes": {"md5": "0" * 32, "sha256": "b" * 64, "simhash": None, "phash": None},
        },
        {
            **_record("r_audio", "", "c" * 64),
            "modal": "audio",
            "text": None,
            "partitions": {"modal": "audio", "source": "web_text", "dt": "2026-11-16"},
            "metadata": {"format": "wav", "sizeBytes": 10, "sha256": "c" * 64,
                         "extra": {"file": "wav.wav", "derivedFrom": "r_video"}},
            "hashes": {"md5": "0" * 32, "sha256": "c" * 64, "simhash": None, "phash": None},
        },
        {
            **_record("r_text2", "文本2", "d" * 64),
            "metadata": {"format": "txt", "sizeBytes": 6, "sha256": "d" * 64,
                         "extra": {"file": "batch.zip/t.txt"}},
        },
    ]
    associations = OP2.index.build_associations(records)
    assert any(item["level"] == "file" and item.get("hasDerivedStream") for item in associations)
    archive = [item for item in associations if item["level"] == "archive"]
    assert archive and archive[0]["modalCounts"]["video"] == 1
    stats = OP2.index.partition_stats(records)
    assert stats["modal=text/source=web_text/dt=2026-11-16"]["records"] == 2


def test_anomaly_detection(tmp_path):
    cfg = OP2.load_config("normalize.json")
    record = _record("r_silent", "", "e" * 64)
    record["modal"] = "audio"
    record["text"] = None
    record["metadata"]["extra"] = {"vad": {"silenceRatio": 1.0}, "file": "a.wav"}
    record["quality"]["emptyText"] = False
    anomalies = OP2.index.detect_anomalies(
        record, records_root=tmp_path, cfg=cfg, standardization_notes=[]
    )
    assert {item["type"] for item in anomalies} == {"SILENT_AUDIO"}
    record["quality"]["emptyText"] = True
    assert json.dumps(anomalies)  # 保持结果可序列化
