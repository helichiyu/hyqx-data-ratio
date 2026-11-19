"""S0 契约测试基座：临时输入/输出目录 + 全部算子骨架 + 测试用 Stub 引擎。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DIR = REPO_ROOT / "operator"
if str(OPERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATOR_DIR))

import inference  # noqa: E402

MAP_PAYLOAD = json.loads((OPERATOR_DIR / "map.json").read_text(encoding="utf-8"))
OPERATORS = MAP_PAYLOAD["operators"]
OPERATOR_IDS = [item["operatorId"] for item in OPERATORS]


class StubCore:
    """仅用于验证 HTTP 层幂等/缓存，不参与任何算子验收。"""

    OPERATOR_VERSION = "0.1.0"

    def run(self, input_path, params=None, seed=None, output_dir=None):
        output = Path(output_dir)
        (output / "result.jsonl").write_text(
            json.dumps({"input": str(input_path), "seed": seed}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return {
            "sampleCount": 1,
            "successCount": 1,
            "failedCount": 0,
            "metrics": {"stubSamples": 1},
            "artifacts": [],
        }


@pytest.fixture()
def app_env(tmp_path):
    app = inference.create_app(tmp_path / "input", tmp_path / "output")
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            app=app,
            input_root=app.state.input_root,
            output_root=app.state.output_root,
            tmp_path=tmp_path,
        )


@pytest.fixture()
def stub_env(tmp_path):
    registry = {
        "_stub": {
            "operatorId": "_stub",
            "semanticCode": "test_stub_v1",
            "requiresWeights": False,
            "version": "0.1.0",
            "core": StubCore(),
        }
    }
    app = inference.create_app(
        tmp_path / "input",
        tmp_path / "output",
        registry=registry,
        max_upload_bytes=1024,
        max_extract_bytes=4096,
    )
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            app=app,
            input_root=app.state.input_root,
            output_root=app.state.output_root,
            tmp_path=tmp_path,
        )


def upload_text(client, operator_id: str, unique_id: str, payload: bytes = b"hello corpus"):
    return client.post(
        f"/{operator_id}/uploadFile",
        data={"uniqueId": unique_id},
        files={"file": ("sample.txt", payload, "text/plain")},
    )
