"""22 个算子的五端点契约测试（S0-2 / S0-4）。

骨架 predict 必须返回业务失败 ``OPERATOR_NOT_IMPLEMENTED``，不得伪造成功结果；
同一输入/参数/seed 重跑必须落到同一 runId。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

OPERATORS = json.loads(
    (Path(__file__).resolve().parents[1] / "operator" / "map.json").read_text(encoding="utf-8")
)["operators"]
PAYLOAD = "数据配比中心 S0 契约测试".encode("utf-8")


def _upload(client, operator_id: str, unique_id: str):
    return client.post(
        f"/{operator_id}/uploadFile",
        data={"uniqueId": unique_id},
        files={"file": ("sample.txt", PAYLOAD, "text/plain")},
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
    assert upload_body["data"]["files"] == ["sample.txt"]
    file_path = upload_body["data"]["filePaths"][0]

    predict = app_env.client.post(
        f"/{operator_id}/predict",
        json={"uniqueId": unique_id, "params": {"k": 1}, "seed": 42},
    )
    assert predict.status_code == 200
    predict_body = predict.json()
    assert predict_body["code"] == 1
    data = predict_body["data"]
    assert data["reasonCode"] == "OPERATOR_NOT_IMPLEMENTED"
    assert data["operatorId"] == operator_id
    assert data["operatorVersion"] == meta["version"]
    assert data["seed"] == 42
    assert data["paramsHash"].startswith("sha256:")
    assert len(data["runId"]) == 16

    rerun = app_env.client.post(
        f"/{operator_id}/predict",
        json={"uniqueId": unique_id, "params": {"k": 1}, "seed": 42},
    )
    assert rerun.status_code == 200
    assert rerun.json()["data"]["runId"] == data["runId"]

    download = app_env.client.get(f"/{operator_id}/downloadFile", params={"path": file_path})
    assert download.status_code == 200
    assert download.content == PAYLOAD

    removed = app_env.client.post(f"/{operator_id}/removeFile", json={"uniqueId": unique_id})
    assert removed.status_code == 200
    assert removed.json()["data"]["removed"] is True

    removed_again = app_env.client.post(f"/{operator_id}/removeFile", json={"uniqueId": unique_id})
    assert removed_again.status_code == 200
    assert removed_again.json()["data"]["removed"] is False
