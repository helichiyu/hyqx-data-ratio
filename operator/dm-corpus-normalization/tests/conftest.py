"""OP-02 测试基座：加载 OP-01/OP-02 核心与样例路径。"""

from __future__ import annotations

import pytest

from op02_env import OP1, OP2, SAMPLES


@pytest.fixture(scope="session")
def op1():
    return OP1


@pytest.fixture(scope="session")
def op2():
    return OP2


@pytest.fixture(scope="session")
def samples():
    return SAMPLES
