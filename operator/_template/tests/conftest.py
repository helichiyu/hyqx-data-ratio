"""模板算子的契约冒烟测试基座（S0-4）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

OPERATOR_DIR = Path(__file__).resolve().parents[2]
if str(OPERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATOR_DIR))

import inference  # noqa: E402


@pytest.fixture()
def template_env(tmp_path):
    registry = {
        "_template": {
            "operatorId": "_template",
            "semanticCode": "template_smoke_v1",
            "requiresWeights": False,
            "version": "0.1.0",
            "core": inference._import_operator_core("_template"),
        }
    }
    app = inference.create_app(tmp_path / "input", tmp_path / "output", registry=registry)
    with TestClient(app) as client:
        yield client
