"""22 个算子的五端点契约测试（S0-2 / S0-4，S1 起按实现状态分流）。

- 骨架算子的 predict 必须返回业务失败 ``OPERATOR_NOT_IMPLEMENTED``，不得伪造成功结果；
- 已实现算子（``map.json.status != "scaffold"``）必须返回成功信封，并写产物；
- 同一输入/参数/seed 重跑必须落到同一 runId；已实现算子第二次命中文档缓存。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

OPERATORS = json.loads(
    (Path(__file__).resolve().parents[1] / "operator" / "map.json").read_text(encoding="utf-8")
)["operators"]
PAYLOAD = "数据配比中心 S0 契约测试".encode("utf-8")
IMPLEMENTED = {
    item["operatorId"] for item in OPERATORS if item.get("status") != "scaffold"
}


def _upload_payload(operator_id: str) -> tuple[str, bytes, str]:
    if operator_id == "dm-label-governance":
        row = {
            "record_id": "r_contract_labels",
            "labels": [
                {
                    "path": ["新闻与资讯", "科技新闻", "产品发布与行业动态"],
                    "confidence": 0.8,
                    "sourceKey": "labels",
                }
            ],
            "unclassified": False,
        }
        return (
            "result.jsonl",
            (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"),
            "application/jsonl",
        )
    if operator_id in {
        "dm-corpus-normalization",
        "dm-text-clustering",
        "dm-multimodal-labeling",
        "dm-taxonomy-labeling",
        "dm-corpus-profiling",
        "dm-language-profiling",
        "dm-text-profiling",
        "dm-quality-analysis",
        "dm-stratified-sampling",
        "dm-knowledge-analysis",
        "dm-speech-analysis",
        "dm-visual-analysis",
    }:
        text = PAYLOAD.decode("utf-8")
        sha = hashlib.sha256(PAYLOAD).hexdigest()
        md5 = hashlib.md5(PAYLOAD, usedforsecurity=False).hexdigest()
        modal = "text"
        if operator_id == "dm-speech-analysis":
            modal = "audio"
        elif operator_id == "dm-visual-analysis":
            modal = "image"
        record = {
            "record_id": "r_contract_op02",
            "modal": modal,
            "source": "web_text",
            "text": text if modal == "text" else None,
            "metadata": {
                "format": "txt",
                "sizeBytes": len(PAYLOAD),
                "sha256": sha,
                "md5": md5,
            },
            "quality": {"decodable": True, "completeness": 1.0, "emptyText": False},
            "partitions": {"modal": "text", "source": "web_text", "dt": "2026-11-16"},
            "hashes": {"md5": md5, "sha256": sha, "simhash": None, "phash": None},
        }
        return "records.jsonl", (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"), "application/jsonl"
    return "sample.txt", PAYLOAD, "text/plain"


def _upload(client, operator_id: str, unique_id: str):
    name, payload, content_type = _upload_payload(operator_id)
    return client.post(
        f"/{operator_id}/uploadFile",
        data={"uniqueId": unique_id},
        files={"file": (name, payload, content_type)},
    )


@pytest.mark.parametrize("meta", OPERATORS, ids=[item["operatorId"] for item in OPERATORS])
def test_operator_five_endpoints(meta, app_env):
    operator_id = meta["operatorId"]
    unique_id = f"contract-{meta['opId'].lower()}"

    health = app_env.client.get(f"/{operator_id}/healthz")
    assert health.status_code == 200
    body = health.json()
    assert body["code"] == 0
    assert body["data"]["ready"] is True
    assert body["data"]["operatorId"] == operator_id
    assert body["data"]["semanticCode"] == meta["semanticCode"]
    assert body["data"]["dependencyStatus"]["core"] == "ok"
    assert set(body["data"]) >= {"ready", "device", "weightsOk", "dependencyStatus"}

    upload = _upload(app_env.client, operator_id, unique_id)
    assert upload.status_code == 200
    upload_body = upload.json()
    assert upload_body["code"] == 0
    assert len(upload_body["data"]["files"]) == 1
    file_path = upload_body["data"]["filePaths"][0]

    predict = app_env.client.post(
        f"/{operator_id}/predict",
        json={"uniqueId": unique_id, "params": {"k": 1}, "seed": 42},
    )
    assert predict.status_code == 200
    predict_body = predict.json()
    data = predict_body["data"]
    assert data["operatorId"] == operator_id
    assert data["operatorVersion"] == meta["version"]
    assert data["seed"] == 42
    assert data["paramsHash"].startswith("sha256:")
    assert len(data["runId"]) == 16

    if operator_id in IMPLEMENTED:
        assert predict_body["code"] == 0
        assert data["sampleCount"] >= 1
        assert (data["successCount"] or 0) + (data["failedCount"] or 0) == data["sampleCount"]
        assert data["outputFilePath"]
        assert Path(data["outputFilePath"]).exists()
    else:
        assert predict_body["code"] == 1
        assert data["reasonCode"] == "OPERATOR_NOT_IMPLEMENTED"

    rerun = app_env.client.post(
        f"/{operator_id}/predict",
        json={"uniqueId": unique_id, "params": {"k": 1}, "seed": 42},
    )
    assert rerun.status_code == 200
    assert rerun.json()["data"]["runId"] == data["runId"]
    if operator_id in IMPLEMENTED:
        assert rerun.json()["data"]["cached"] is True

    download = app_env.client.get(f"/{operator_id}/downloadFile", params={"path": file_path})
    assert download.status_code == 200
    assert download.content.startswith(_upload_payload(operator_id)[1][:32])

    removed = app_env.client.post(f"/{operator_id}/removeFile", json={"uniqueId": unique_id})
    assert removed.status_code == 200
    assert removed.json()["data"]["removed"] is True

    removed_again = app_env.client.post(f"/{operator_id}/removeFile", json={"uniqueId": unique_id})
    assert removed_again.status_code == 200
    assert removed_again.json()["data"]["removed"] is False
