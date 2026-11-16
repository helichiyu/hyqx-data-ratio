"""OP-07 测试：树校验、非法路径、冲突、PII、无审核指标。"""

from __future__ import annotations

import json

from op07_env import CORE


def test_trees_and_nearest():
    cfg = CORE.load_config()
    trees = CORE.rules.Trees(cfg)
    assert trees.tree_version == "taxonomy-1013-pending"
    valid = list(trees.all_paths)[0]
    assert trees.is_valid(list(valid))
    illegal = list(valid[:-1]) + ["不存在的节点"]
    nearest = trees.nearest(illegal, 10)
    assert nearest is not None
    assert nearest["distance"] <= 10


def test_conflicts_and_pii():
    cfg = CORE.load_config()
    labels = [
        {"path": ["A", "B", "C"], "confidence": 0.8},
        {"path": ["A", "B", "C"], "confidence": 0.3},
        {"path": ["D", "E", "F"], "confidence": 0.7},
    ]
    conflicts = CORE.rules.detect_conflicts("r_1", labels, cfg)
    assert any(item["type"] == "DUPLICATE_PATH" for item in conflicts)
    assert any(item["type"] == "CROSS_DOMAIN_CONFLICT" for item in conflicts)

    hits = CORE.rules.pii_scan("联系 13800138000 或 test@example.com", cfg)
    assert {item["type"] for item in hits} == {"mobile_cn", "email"}
    assert all("*" in item["value"] for item in hits)


def test_core_governance_report(tmp_path):
    rows = [
        {
            "record_id": "r_ok",
            "labels": [{"path": ["新闻与资讯", "科技新闻", "产品发布与行业动态"],
                        "confidence": 0.6, "sourceKey": "labels"}],
            "unclassified": False,
        },
        {
            "record_id": "r_illegal",
            "labels": [{"path": ["不存在的一级", "不存在", "不存在"], "confidence": 0.9}],
            "unclassified": False,
        },
        {
            "record_id": "r_conflict",
            "labels": [
                {"path": ["新闻与资讯", "科技新闻", "产品发布与行业动态"], "confidence": 0.8},
                {"path": ["知识与参考", "科普与专著", "学术专著"], "confidence": 0.7},
            ],
            "unclassified": False,
        },
        {
            "record_id": "r_unclassified",
            "labels": [],
            "unclassified": True,
            "reasonCode": "UNCLASSIFIED_SMALL_MARGIN",
            "evidence": {"preview": "电话 13800138000"},
        },
    ]
    source = tmp_path / "result.jsonl"
    source.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    result = CORE.run(str(source), params={}, seed=42, output_dir=str(tmp_path / "out"))
    assert result["sampleCount"] == 4
    assert result["failedCount"] == 2  # illegal + conflict
    metrics = result["metrics"]
    assert metrics["illegalLabels"] == 1
    assert metrics["conflicts"] >= 1
    assert metrics["piiRecords"] == 1
    assert metrics["unclassifiedByReason"] == {"UNCLASSIFIED_SMALL_MARGIN": 1}
    assert metrics["reviewMetrics"]["kappa"] is None
    assert metrics["reviewMetrics"]["blockedReason"] == "REVIEW_RECORDS_REQUIRED"
    assert (tmp_path / "out" / "illegal.jsonl").read_text(encoding="utf-8").strip()
    report = json.loads((tmp_path / "out" / "governance_report.json").read_text(encoding="utf-8"))
    assert report["legalRate"] < 1.0
