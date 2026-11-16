"""OP-02 测试环境（唯一模块名，避免多算子 tests 目录同名冲突）。"""

from __future__ import annotations

import sys
from pathlib import Path

OPERATOR_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(OPERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATOR_DIR))

import inference  # noqa: E402

OP1 = inference._import_operator_core("dm-multimodal-analysis")
OP2 = inference._import_operator_core("dm-corpus-normalization")
SAMPLES = REPO_ROOT / "docs" / "算子开发" / "samples"
