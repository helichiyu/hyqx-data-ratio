"""AHP：判断矩阵权重、最大特征值、CI 与 CR。

口径：
- 权重 = 判断矩阵最大特征值对应的特征向量（正矩阵，反幂/幂迭代求主特征向量），归一化后求和为 1；
- λmax = Σ (A·w)_i / w_i 的均值；CI = (λmax - n) / (n - 1)；
- CR = CI / RI，4 阶 RI = 0.90；CR < 0.1 视为通过。
"""

from __future__ import annotations

from typing import Any

import numpy as np

RI_TABLE = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}


def principal_weight(matrix: list[list[float]], iterations: int = 100) -> np.ndarray:
    """幂迭代求主特征向量并归一化。"""

    a = np.asarray(matrix, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError("判断矩阵必须为方阵")
    vector = np.full(a.shape[0], 1.0 / a.shape[0])
    for _ in range(iterations):
        updated = a @ vector
        total = updated.sum()
        if total <= 0:
            raise ValueError("判断矩阵存在非正列，无法求权重")
        vector = updated / total
    return vector


def consistency(matrix: list[list[float]]) -> dict[str, Any]:
    a = np.asarray(matrix, dtype=np.float64)
    n = a.shape[0]
    weights = principal_weight(matrix)
    weighted = a @ weights
    lambda_max = float(np.mean(weighted / weights))
    ci = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    ri = RI_TABLE.get(n, 1.45)
    cr = max(0.0, ci / ri) if ri else 0.0
    return {
        "n": n,
        "weights": [round(float(item), 6) for item in weights],
        "lambdaMax": round(lambda_max, 6),
        "ci": round(float(ci), 6),
        "ri": ri,
        "cr": round(float(cr), 6),
    }
