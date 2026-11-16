"""runId 确定性与幂等重跑测试（S0-2）。

runId = sha256(输入指纹 + operatorVersion + paramsHash + seed)[:16]；
同一输入/版本/参数/seed 必须落到同一目录，第二次返回缓存结果，不产生第二份产物。
"""

from __future__ import annotations

from pathlib import Path


def _upload(client, unique_id: str, payload: bytes = b"idempotent corpus"):
    response = client.post(
        "/_stub/uploadFile",
        data={"uniqueId": unique_id},
        files={"file": ("sample.txt", payload, "text/plain")},
    )
    assert response.status_code == 200
    return response.json()["data"]["filePaths"][0]


def test_success_is_cached_and_single_run_dir(stub_env):
    _upload(stub_env.client, "cache")
    first = stub_env.client.post("/_stub/predict", json={"uniqueId": "cache", "params": {"k": 1}, "seed": 7})
    assert first.status_code == 200
    assert first.json()["code"] == 0
    data = first.json()["data"]
    assert data["cached"] is False
    run_dir = Path(data["outputDir"])
    assert run_dir.is_dir()
    assert (run_dir / "result.json").is_file()

    second = stub_env.client.post("/_stub/predict", json={"uniqueId": "cache", "params": {"k": 1}, "seed": 7})
    assert second.status_code == 200
    second_data = second.json()["data"]
    assert second_data["cached"] is True
    assert second_data["runId"] == data["runId"]
    assert second_data["outputDir"] == data["outputDir"]
    assert len(list((stub_env.output_root / "_stub").iterdir())) == 1


def test_seed_and_params_change_run_id(stub_env):
    _upload(stub_env.client, "keys")
    base = stub_env.client.post("/_stub/predict", json={"uniqueId": "keys", "params": {"k": 1}, "seed": 7})
    other_seed = stub_env.client.post("/_stub/predict", json={"uniqueId": "keys", "params": {"k": 1}, "seed": 8})
    other_params = stub_env.client.post("/_stub/predict", json={"uniqueId": "keys", "params": {"k": 2}, "seed": 7})
    run_ids = {
        base.json()["data"]["runId"],
        other_seed.json()["data"]["runId"],
        other_params.json()["data"]["runId"],
    }
    assert len(run_ids) == 3


def test_same_content_different_unique_id_same_run_id(stub_env):
    _upload(stub_env.client, "one", b"same-bytes")
    _upload(stub_env.client, "two", b"same-bytes")
    first = stub_env.client.post("/_stub/predict", json={"uniqueId": "one", "seed": 1})
    second = stub_env.client.post("/_stub/predict", json={"uniqueId": "two", "seed": 1})
    assert first.json()["data"]["runId"] == second.json()["data"]["runId"]


def test_default_seed_is_recorded(stub_env):
    _upload(stub_env.client, "default-seed")
    response = stub_env.client.post("/_stub/predict", json={"uniqueId": "default-seed"})
    assert response.status_code == 200
    assert response.json()["data"]["seed"] == 42
