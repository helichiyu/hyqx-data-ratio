"""OP-01 测试基座：加载同名包核心与样例路径。"""

from __future__ import annotations

import json

import pytest

from op01_env import CORE, SAMPLES, SCHEMAS


@pytest.fixture(scope="session")
def core():
    return CORE


@pytest.fixture(scope="session")
def samples():
    return SAMPLES


@pytest.fixture(scope="session")
def record_schema() -> dict:
    return json.loads((SCHEMAS / "record.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def manifest_schema() -> dict:
    return json.loads((SCHEMAS / "manifest.schema.json").read_text(encoding="utf-8"))
