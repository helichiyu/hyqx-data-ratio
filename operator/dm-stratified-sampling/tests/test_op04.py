"""OP-04 单测与端到端：Neyman 配额、确定性抽样、边界与幂等。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from op04_env import CORE, OP02_EVIDENCE

neyman = CORE.neyman
sampler = CORE.sampler
strata = CORE.strata
cfg = CORE.load_config()


def _stratum(values: list[float]) -> dict:
    return {"records": [f"r{index}" for index in range(len(values))], "values": values}


def test_neyman_allocates_by_n_times_cv():
    data = {
        "a": _stratum([1.0, 2.0, 3.0, 4.0]),   # N=4, CV≈0.447
        "b": _stratum([10.0] * 4),             # N=4, CV=0
    }
    caps = {"a": 4, "b": 4}
    result = neyman.allocate(data, target=4, min_per_stratum=1, max_per_stratum=caps)
    assert result["basis"] == "neyman"
    assert result["allocated"] == 4
    assert result["quotas"]["a"] >= 3
    assert result["quotas"]["b"] == 1


def test_neyman_proportional_when_cv_zero():
    data = {"a": _stratum([5.0] * 6), "b": _stratum([5.0] * 2)}
    caps = {"a": 6, "b": 2}
    result = neyman.allocate(data, target=4, min_per_stratum=1, max_per_stratum=caps)
    assert result["basis"] == "proportional(no-cv)"
    assert result["quotas"] == {"a": 3, "b": 1}
    assert result["unmet"] == 0


def test_neyman_respects_capacity_and_reports_unmet():
    data = {"a": _stratum([1.0, 2.0])}
    result = neyman.allocate(data, target=5, min_per_stratum=1, max_per_stratum={"a": 2})
    assert result["quotas"]["a"] == 2
    assert result["unmet"] == 3


def test_sampler_deterministic_and_no_duplicates():
    records = [f"r{index}" for index in range(100)]
    first = sampler.sample_stratum(records, 10, seed=42)
    second = sampler.sample_stratum(records, 10, seed=42)
    assert [item["record_id"] for item in first] == [item["record_id"] for item in second]
    assert len({item["record_id"] for item in first}) == 10


def test_strata_missing_marker():
    record = {"record_id": "r1", "source": "web_text"}
    key = strata.stratum_key(record, {}, {}, cfg)
    assert key == "web_text|MISSING|MISSING"


def _record(record_id: str, text: str, source: str = "web_text") -> dict:
    return {
        "record_id": record_id,
        "modal": "text",
        "source": source,
        "text": text,
        "metadata": {"format": "txt", "sizeBytes": len(text.encode())},
        "quality": {"completeness": 1.0, "decodable": True},
        "partitions": {"dt": "2026-11-16", "modal": "text", "source": source},
        "hashes": {"md5": "0" * 32, "sha256": "0" * 64},
    }


def test_core_sampling_and_bias(tmp_path: Path):
    records = [
        _record("r1", "一二三四五", "web_text"),
        _record("r2", "六七八九十", "web_text"),
        _record("r3", "abcdefghij", "books"),
        _record("r4", "klmnopqrst", "books"),
    ]
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8"
    )
    result = CORE.run(str(input_dir), {"share": 0.5}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert metrics["population"] == 4
    assert metrics["target"] == 2
    assert metrics["sampled"] == 2
    assert metrics["targetMet"] is True
    assert metrics["duplicateFree"] is True
    assert metrics["skippedDimensions"] == {"cluster": "MISSING", "quality": "MISSING"}
    quota = json.loads((tmp_path / "out" / "quota_table.json").read_text(encoding="utf-8"))
    assert len(quota["strata"]) == 2
    assert all(row["quota"] == row["sampled"] for row in quota["strata"])


def test_core_min_total_flagged(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        json.dumps(_record("r1", "文本"), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    assert result["metrics"]["minTotalMet"] is False
    assert result["metrics"]["sampled"] == 1


def test_core_idempotent(tmp_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "records.jsonl").write_text(
        "\n".join(
            json.dumps(_record(f"r{index}", f"文本内容{index}"), ensure_ascii=False)
            for index in range(20)
        )
        + "\n",
        encoding="utf-8",
    )
    CORE.run(str(input_dir), {"share": 0.5}, 42, str(tmp_path / "a"))
    CORE.run(str(input_dir), {"share": 0.5}, 42, str(tmp_path / "b"))
    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_core_real_op02_batch(tmp_path: Path):
    if not (OP02_EVIDENCE / "records.jsonl").is_file():
        import pytest

        pytest.skip("缺少 OP-02 证据目录")
    result = CORE.run(str(OP02_EVIDENCE), {"share": 0.1}, 42, str(tmp_path / "real"))
    metrics = result["metrics"]
    assert metrics["population"] == 432
    assert metrics["target"] == metrics["sampled"]
    assert metrics["stratumCount"] >= 1
    assert metrics["maxAbsBias"] >= 0.0
