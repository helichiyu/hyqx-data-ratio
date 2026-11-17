"""OP-17 测试环境（唯一模块名）。"""

from __future__ import annotations

import sys
from pathlib import Path

OPERATOR_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(OPERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATOR_DIR))

import inference  # noqa: E402

CORE = inference._import_operator_core("dm-dataset-packaging")

OP15_EVIDENCE = REPO_ROOT / "operator" / "dm-ratio-computation" / "output" / "evidence"
OP02_EVIDENCE = REPO_ROOT / "operator" / "dm-corpus-normalization" / "output" / "evidence"
OP05_EVIDENCE = REPO_ROOT / "operator" / "dm-multimodal-labeling" / "output" / "evidence"


def latest_run(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    candidates = [path for path in root.iterdir() if path.is_dir()]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None
