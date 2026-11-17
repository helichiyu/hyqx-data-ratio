"""OP-16 测试环境（唯一模块名）。"""

from __future__ import annotations

import sys
from pathlib import Path

OPERATOR_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(OPERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATOR_DIR))

import inference  # noqa: E402

CORE = inference._import_operator_core("dm-ratio-analysis")
OP15_EVIDENCE_ROOT = OPERATOR_DIR / "dm-ratio-computation" / "output" / "evidence"


def latest_op15_evidence() -> Path | None:
    if not OP15_EVIDENCE_ROOT.is_dir():
        return None
    candidates = [
        path
        for path in OP15_EVIDENCE_ROOT.iterdir()
        if path.is_dir() and (path / "plan.json").is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)
