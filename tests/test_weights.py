"""权重根解析：WEIGHTS_DIR 覆盖与 healthz.weightsOk。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import inference


def test_weights_ok_reads_weights_dir(tmp_path, monkeypatch):
    model = tmp_path / "shared" / "bge-base-zh-v1.5"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("WEIGHTS_DIR", str(tmp_path))
    app = inference.create_app(tmp_path / "input", tmp_path / "output")
    with TestClient(app) as client:
        data = client.get("/dm-taxonomy-labeling/healthz").json()["data"]
    assert data["weightsOk"] is True


def test_weights_ok_false_without_files(tmp_path, monkeypatch):
    monkeypatch.setenv("WEIGHTS_DIR", str(tmp_path / "empty"))
    app = inference.create_app(tmp_path / "input", tmp_path / "output")
    with TestClient(app) as client:
        data = client.get("/dm-taxonomy-labeling/healthz").json()["data"]
    assert data["weightsOk"] is False
