"""双后端模型网关：后端解析、签名头与凭据检查。"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "operator") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "operator"))

import model_gateway  # noqa: E402


@pytest.fixture()
def fresh_module(monkeypatch):
    """清掉与 backend 相关的环境变量，逐用例隔离。"""

    for name in ("MODEL_BACKEND", "MODEL_GATEWAY_BASE_URL", "MODEL_APP_ID",
                 "MODEL_APP_KEY", "MODEL_CAPABILITY", "SILICONFLOW_BASE_URL",
                 "SILICONFLOW_API_KEY", "MODEL_GATEWAY_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return model_gateway


def test_resolve_backend_default_and_aliases(fresh_module):
    assert fresh_module.resolve_backend({}) == "idg"
    assert fresh_module.resolve_backend({"MODEL_BACKEND": "siliconflow"}) == "siliconflow"
    assert fresh_module.resolve_backend({"MODEL_BACKEND": "IDG"}) == "idg"
    assert fresh_module.resolve_backend({"MODEL_BACKEND": "panzhi"}) == "idg"
    assert fresh_module.resolve_backend({"MODEL_BACKEND": "prod"}) == "idg"
    assert fresh_module.resolve_backend({"MODEL_BACKEND": "sf"}) == "siliconflow"
    assert fresh_module.resolve_backend({"MODEL_BACKEND": "test"}) == "siliconflow"
    assert fresh_module.resolve_backend({"MODEL_BACKEND": "nonsense"}) == "idg"


def test_panzhi_headers_signature(fresh_module):
    env = {"MODEL_APP_ID": "audioasr", "MODEL_APP_KEY": "secret-key"}
    headers = fresh_module.panzhi_headers("/Qwen3.5-9B", env)
    assert headers["appKey"] == "secret-key"
    # 校验和可复算：md5(APPKEY + X-CurTime + X-Server-Param)
    expected = hashlib.md5(
        ("secret-key" + headers["X-CurTime"] + headers["X-Server-Param"]).encode("utf-8")
    ).hexdigest()
    assert headers["X-CheckSum"] == expected
    # X-Server-Param 解码后为 {appid, csid}，csid = appid + capability 补 0 到 24 位 + uuid
    payload = json.loads(base64.b64decode(headers["X-Server-Param"]))
    assert payload["appid"] == "audioasr"
    assert payload["csid"].startswith("audioasr" + "Qwen3.5-9B".ljust(24, "0"))
    assert len(payload["csid"]) == len("audioasr") + 24 + 32


def test_panzhi_headers_capability_override_and_errors(fresh_module):
    env = {"MODEL_APP_ID": "audioasr", "MODEL_APP_KEY": "k", "MODEL_CAPABILITY": "myCap"}
    headers = fresh_module.panzhi_headers("/some/path", env)
    payload = json.loads(base64.b64decode(headers["X-Server-Param"]))
    assert payload["csid"].startswith("audioasr" + "myCap".ljust(24, "0"))

    with pytest.raises(model_gateway.GatewayError):
        fresh_module.panzhi_headers("/Qwen3.5-9B", {"MODEL_APP_ID": "a"})  # 缺 APPKEY


def test_models_table_consistency(fresh_module):
    for role, spec in fresh_module.MODELS["idg"].items():
        assert spec.get("path"), f"idg/{role} 缺 path"
        assert spec.get("model"), f"idg/{role} 缺 model"
        assert spec["path"].startswith("/")
    for role, spec in fresh_module.MODELS["siliconflow"].items():
        assert spec.get("model"), f"siliconflow/{role} 缺 model"


def test_backend_status_reports_missing(fresh_module):
    status = fresh_module.backend_status({})
    assert status["backend"] == "idg"
    assert "MODEL_GATEWAY_BASE_URL" in status["missing"]
    assert "MODEL_APP_KEY" in status["missing"]
    assert status["credentialsOk"] is False

    status = fresh_module.backend_status({"MODEL_BACKEND": "siliconflow"})
    assert status == {"backend": "siliconflow", "credentialsOk": False,
                      "missing": ["SILICONFLOW_API_KEY"]}

    ok = fresh_module.backend_status({
        "MODEL_GATEWAY_BASE_URL": "http://10.0.0.1:9050", "MODEL_APP_KEY": "k"})
    assert ok["credentialsOk"] is True


def test_siliconflow_key_priority_and_alias(fresh_module):
    assert fresh_module.siliconflow_key({"SILICONFLOW_API_KEY": "new"}) == "new"
    assert fresh_module.siliconflow_key({"MODEL_GATEWAY_API_KEY": "legacy"}) == "legacy"
    assert fresh_module.siliconflow_key(
        {"SILICONFLOW_API_KEY": "new", "MODEL_GATEWAY_API_KEY": "legacy"}) == "new"
    with pytest.raises(model_gateway.GatewayError):
        fresh_module.siliconflow_key({})
