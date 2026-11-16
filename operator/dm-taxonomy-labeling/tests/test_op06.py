"""OP-06 测试：双树空间、多标签、未明确与幂等。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from op06_env import CORE, SAMPLE


def test_domain_ability_trees_separated():
    cfg = CORE.load_config()
    domain = CORE.tree.LabelTree(cfg["tree"]["relativePath"], "domain")
    ability = CORE.tree.LabelTree(cfg["tree"]["relativePath"], "ability")
    assert len(domain.labels) == 209
    assert len(ability.labels) == 65
    assert domain.tree_version == ability.tree_version == "taxonomy-1013-pending"
    assert not (set(map(tuple, [item["path"] for item in domain.labels]))
                & set(map(tuple, [item["path"] for item in ability.labels])))


def test_core_multilabel_and_idempotent(tmp_path):
    first = CORE.run(str(SAMPLE), params={}, seed=42, output_dir=str(tmp_path / "a"))
    second = CORE.run(str(SAMPLE), params={}, seed=42, output_dir=str(tmp_path / "b"))
    assert first["sampleCount"] == 2
    assert first["metrics"]["spacesSeparated"] is True
    assert first["metrics"]["labelSpaceSizes"] == {"domain": 209, "ability": 65}
    rows = [
        json.loads(line)
        for line in (tmp_path / "a" / "result.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    for row in rows:
        for key in ("domainLabels", "abilityLabels"):
            assert len(row[key]) <= 3
            for label in row[key]:
                assert label["path"]
                assert 0 <= label["confidence"] <= 1
        assert row["domainUnknown"] in (True, False)
    assert any(row["domainLabels"] for row in rows)
    left = (tmp_path / "a" / "result.jsonl").read_bytes()
    right = (tmp_path / "b" / "result.jsonl").read_bytes()
    assert hashlib.sha256(left).hexdigest() == hashlib.sha256(right).hexdigest()


def test_empty_text_unknown(tmp_path):
    record = {
        "record_id": "r_empty",
        "modal": "text",
        "source": "web_text",
        "text": "",
        "metadata": {"format": "txt", "sizeBytes": 0, "sha256": "0" * 64},
        "quality": {"decodable": True, "completeness": 1.0, "emptyText": True},
        "partitions": {"modal": "text", "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": "0" * 32, "sha256": "0" * 64},
    }
    source = tmp_path / "records.jsonl"
    source.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    result = CORE.run(str(source), params={}, seed=42, output_dir=str(tmp_path / "out"))
    row = json.loads((tmp_path / "out" / "result.jsonl").read_text(encoding="utf-8"))
    assert row["domainUnknown"] is True
    assert row["abilityUnknown"] is True
    assert result["failedCount"] == 1
