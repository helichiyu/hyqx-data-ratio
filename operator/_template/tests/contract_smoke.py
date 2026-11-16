"""在 _template 上跑通五端点、路径闸门与业务失败信封。"""

from __future__ import annotations


def _reason(response) -> str:
    return response.json()["data"]["reasonCode"]


def test_template_contract(template_env):
    health = template_env.get("/_template/healthz")
    assert health.status_code == 200
    assert health.json()["code"] == 0
    assert health.json()["data"]["ready"] is True

    upload = template_env.post(
        "/_template/uploadFile",
        data={"uniqueId": "template"},
        files={"file": ("demo.txt", b"template corpus", "text/plain")},
    )
    assert upload.status_code == 200
    assert upload.json()["code"] == 0
    file_path = upload.json()["data"]["filePaths"][0]

    predict = template_env.post("/_template/predict", json={"uniqueId": "template"})
    assert predict.status_code == 200
    assert predict.json()["code"] == 1
    assert _reason(predict) == "OPERATOR_NOT_IMPLEMENTED"

    download = template_env.get("/_template/downloadFile", params={"path": file_path})
    assert download.status_code == 200
    assert download.content == b"template corpus"

    remove = template_env.post("/_template/removeFile", json={"uniqueId": "template"})
    assert remove.status_code == 200
    assert remove.json()["data"]["removed"] is True


def test_template_path_gate(template_env):
    outside = template_env.get("/_template/downloadFile", params={"path": "relative.txt"})
    assert outside.status_code == 400
    assert _reason(outside) == "PATH_INVALID"
