"""算子核心入口（S0 骨架）。

约定：``core.run(input_path, params, seed, output_dir) -> dict``；
本文件不依赖 FastAPI/HTTP，HTTP 层由仓库根 ``inference.py`` 统一实现。
S0 阶段只声明未实现，不伪造任何计算结果。
"""

from __future__ import annotations

OPERATOR_VERSION = "0.1.0"
REASON_NOT_IMPLEMENTED = "OPERATOR_NOT_IMPLEMENTED"


def run(input_path: str, params: dict | None = None, seed: int | None = None,
        output_dir: str | None = None) -> dict:
    """执行算子计算；S0 阶段只声明未实现，不伪造结果。"""
    raise NotImplementedError(REASON_NOT_IMPLEMENTED)
