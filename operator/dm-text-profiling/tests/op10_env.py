"""OP-10 测试环境（唯一模块名）。"""

from __future__ import annotations

import sys
from pathlib import Path

OPERATOR_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(OPERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATOR_DIR))

import inference  # noqa: E402

CORE = inference._import_operator_core("dm-text-profiling")
OP02_EVIDENCE = (
    REPO_ROOT / "operator" / "dm-corpus-normalization" / "output" / "evidence" / "10a342ae92595ab7"
)
