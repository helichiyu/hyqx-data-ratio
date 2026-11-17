"""运行期设备探针：healthz 必须报告实际设备，不允许"假装 GPU"。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import inference


def test_healthz_reports_actual_device(app_env):
    payload = app_env.client.get("/dm-multimodal-analysis/healthz").json()
    data = payload["data"]
    assert data["device"] in {"cpu", "cuda", "cuda:0", "cuda:1"}
    assert data["deviceRequested"] in {"auto", "cpu", "cuda", "cuda:0", "cuda:1"}
    assert isinstance(data["cudaAvailable"], bool)
    # 报 GPU 时必须真的可用；报 CPU 且请求 auto 时，说明发生了回落或不支持
    if data["device"] != "cpu":
        assert data["cudaAvailable"] is True


def test_healthz_honours_cpu_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVICE", "cpu")
    app = inference.create_app(tmp_path / "input", tmp_path / "output")
    with TestClient(app) as client:
        data = client.get("/dm-multimodal-analysis/healthz").json()["data"]
    assert data["device"] == "cpu"
    assert data["deviceRequested"] == "cpu"
