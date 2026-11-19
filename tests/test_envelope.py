"""统一信封、HTTP 状态码与参数校验测试。"""

from __future__ import annotations

import json
from pathlib import Path

OPERATOR = "dm-multimodal-analysis"
EXPECTED_OPERATORS = len(
    json.loads((Path(__file__).resolve().parents[1] / "operator" / "map.json").read_text(encoding="utf-8"))["operators"]
)


def upload_text(client, operator_id: str, unique_id: str):
    return client.post(
        f"/{operator_id}/uploadFile",
        data={"uniqueId": unique_id},
        files={"file": ("sample.txt", b"hello corpus", "text/plain")},
    )


def _reason(response) -> str:
    return response.json()["data"]["reasonCode"]


def test_aggregate_health(app_env):
    response = app_env.client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"
    assert body["data"]["operatorCount"] == EXPECTED_OPERATORS
    assert body["data"]["readyCount"] == EXPECTED_OPERATORS


def test_unknown_operator_returns_envelope_404(app_env):
    response = app_env.client.get("/dm-not-exists/healthz")
    assert response.status_code == 404
    assert response.json()["code"] == 1
    assert _reason(response) == "NOT_FOUND"


def test_wrong_method_returns_envelope_405(app_env):
    response = app_env.client.put(f"/{OPERATOR}/predict")
    assert response.status_code == 405
    assert _reason(response) == "METHOD_NOT_ALLOWED"


def test_predict_invalid_json(app_env):
    response = app_env.client.post(
        f"/{OPERATOR}/predict",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert _reason(response) == "INVALID_JSON"


def test_predict_requires_input(app_env):
    response = app_env.client.post(f"/{OPERATOR}/predict", json={})
    assert response.status_code == 400
    assert _reason(response) == "INPUT_REQUIRED"


def test_predict_rejects_multiple_inputs(app_env):
    upload = upload_text(app_env.client, OPERATOR, "multi")
    file_path = upload.json()["data"]["filePaths"][0]
    response = app_env.client.post(
        f"/{OPERATOR}/predict",
        json={"uniqueId": "multi", "inputFile": file_path},
    )
    assert response.status_code == 400
    assert _reason(response) == "INVALID_REQUEST"


def test_predict_invalid_params_and_seed(app_env):
    upload_text(app_env.client, OPERATOR, "params")
    bad_params = app_env.client.post(
        f"/{OPERATOR}/predict",
        json={"uniqueId": "params", "params": [1, 2]},
    )
    assert bad_params.status_code == 400
    assert _reason(bad_params) == "INVALID_REQUEST"

    bad_seed = app_env.client.post(
        f"/{OPERATOR}/predict",
        json={"uniqueId": "params", "seed": "abc"},
    )
    assert bad_seed.status_code == 400
    assert _reason(bad_seed) == "INVALID_REQUEST"


def test_predict_missing_input_returns_404(app_env):
    response = app_env.client.post(f"/{OPERATOR}/predict", json={"uniqueId": "absent"})
    assert response.status_code == 404
    assert _reason(response) == "INPUT_NOT_FOUND"


def test_upload_requires_file_field(app_env):
    response = app_env.client.post(f"/{OPERATOR}/uploadFile", data={"uniqueId": "no-file"})
    assert response.status_code == 400
    assert _reason(response) == "INVALID_REQUEST"


def test_upload_rejects_unsupported_suffix(app_env):
    response = app_env.client.post(
        f"/{OPERATOR}/uploadFile",
        data={"uniqueId": "exe"},
        files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert _reason(response) == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_invalid_unique_id(app_env):
    response = app_env.client.post(
        f"/{OPERATOR}/uploadFile",
        data={"uniqueId": "../escape"},
        files={"file": ("a.txt", b"x", "text/plain")},
    )
    assert response.status_code == 400
    assert _reason(response) == "UNIQUE_ID_INVALID"


def test_upload_too_large(stub_env):
    response = stub_env.client.post(
        "/_stub/uploadFile",
        data={"uniqueId": "big"},
        files={"file": ("a.txt", b"x" * 2048, "text/plain")},
    )
    assert response.status_code == 413
    assert _reason(response) == "UPLOAD_TOO_LARGE"


def test_download_missing_query_returns_envelope_400(app_env):
    response = app_env.client.get(f"/{OPERATOR}/downloadFile")
    assert response.status_code == 400
    assert _reason(response) == "INVALID_REQUEST"


def test_remove_invalid_json(app_env):
    response = app_env.client.post(
        f"/{OPERATOR}/removeFile",
        content=b"{",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert _reason(response) == "INVALID_JSON"
