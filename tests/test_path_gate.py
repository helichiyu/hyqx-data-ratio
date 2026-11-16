"""路径闸门、zip-slip、超大文件与幂等重跑测试（S0-2 / S0-9 门禁）。"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest

OPERATOR = "dm-multimodal-analysis"


def _reason(response) -> str:
    return response.json()["data"]["reasonCode"]


@pytest.mark.parametrize(
    "raw",
    [
        "file:///etc/passwd",
        "~/corpus.txt",
        "relative/corpus.txt",
        "\x01control.txt",
    ],
)
def test_path_format_rejected(app_env, raw):
    response = app_env.client.post(f"/{OPERATOR}/predict", json={"inputFile": raw})
    assert response.status_code == 400
    assert _reason(response) == "PATH_INVALID"


def test_path_out_of_bounds(app_env):
    outside = app_env.tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    response = app_env.client.post(f"/{OPERATOR}/predict", json={"inputFile": str(outside)})
    assert response.status_code == 400
    assert _reason(response) == "PATH_OUT_OF_BOUNDS"

    traversal = str(app_env.input_root / ".." / ".." / "outside.txt")
    response = app_env.client.post(f"/{OPERATOR}/predict", json={"inputFile": traversal})
    assert response.status_code == 400
    assert _reason(response) == "PATH_OUT_OF_BOUNDS"


def test_remove_root_forbidden(app_env):
    for root in (app_env.input_root, app_env.output_root):
        response = app_env.client.post(f"/{OPERATOR}/removeFile", json={"path": str(root)})
        assert response.status_code == 400
        assert _reason(response) == "ROOT_PATH_FORBIDDEN"


def test_download_out_of_bounds(app_env):
    outside = app_env.tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    response = app_env.client.get(f"/{OPERATOR}/downloadFile", params={"path": str(outside)})
    assert response.status_code == 400
    assert _reason(response) == "PATH_OUT_OF_BOUNDS"


def test_download_missing_file(app_env):
    missing = app_env.input_root / "absent.txt"
    response = app_env.client.get(f"/{OPERATOR}/downloadFile", params={"path": str(missing)})
    assert response.status_code == 404
    assert _reason(response) == "INPUT_NOT_FOUND"


def test_symlink_rejected(app_env):
    target = app_env.tmp_path / "outside.txt"
    target.write_text("secret", encoding="utf-8")
    link = app_env.input_root / "link.txt"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("当前环境不允许创建符号链接")
    response = app_env.client.post(f"/{OPERATOR}/removeFile", json={"path": str(link)})
    assert response.status_code == 400
    assert _reason(response) == "PATH_SYMLINK"


def test_zip_slip_flattened_inside_destination(app_env):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../evil.txt", "pwn")
        archive.writestr("nested/good.txt", "ok")
        archive.writestr("skip.exe", "no")
    response = app_env.client.post(
        f"/{OPERATOR}/uploadFile",
        data={"uniqueId": "zipslip"},
        files={"file": ("batch.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert sorted(body["data"]["files"]) == ["evil.txt", "good.txt"]
    assert "skip.exe" in body["data"]["skipped"]
    assert not (app_env.tmp_path / "evil.txt").exists()
    assert not (app_env.input_root / "evil.txt").exists()
    assert (app_env.input_root / "zipslip" / "evil.txt").is_file()


def test_invalid_zip(app_env):
    response = app_env.client.post(
        f"/{OPERATOR}/uploadFile",
        data={"uniqueId": "badzip"},
        files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
    )
    assert response.status_code == 400
    assert _reason(response) == "ZIP_INVALID"


def test_zip_without_allowed_members(app_env):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("only.exe", b"MZ")
    response = app_env.client.post(
        f"/{OPERATOR}/uploadFile",
        data={"uniqueId": "emptyzip"},
        files={"file": ("empty.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 400
    assert _reason(response) == "ZIP_EMPTY"


def test_zip_extract_limit(stub_env):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big.txt", b"x" * 5000)
    response = stub_env.client.post(
        "/_stub/uploadFile",
        data={"uniqueId": "bigzip"},
        files={"file": ("big.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 413
    assert _reason(response) == "ZIP_TOO_LARGE"


def test_predict_rejects_zip_without_allowed_members(app_env):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("only.exe", b"MZ")
    archive_path = app_env.input_root / "bad.zip"
    archive_path.write_bytes(buffer.getvalue())
    response = app_env.client.post(f"/{OPERATOR}/predict", json={"inputFile": str(archive_path)})
    assert response.status_code == 400
    assert _reason(response) == "ZIP_INVALID"


def test_upload_size_limit(stub_env):
    response = stub_env.client.post(
        "/_stub/uploadFile",
        data={"uniqueId": "oversize"},
        files={"file": ("big.txt", b"x" * 2048, "text/plain")},
    )
    assert response.status_code == 413
    assert _reason(response) == "UPLOAD_TOO_LARGE"


def test_predict_size_limit(stub_env):
    response = stub_env.client.post(
        "/_stub/predict",
        files={"file": ("big.txt", b"x" * 2048, "text/plain")},
    )
    assert response.status_code == 413
    assert _reason(response) == "UPLOAD_TOO_LARGE"
