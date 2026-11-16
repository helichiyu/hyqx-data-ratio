"""bge-base-zh-v1.5 文本向量：mean pooling + L2 归一化。

模型来自 ``operator/weights/shared/bge-base-zh-v1.5``（MIT，可商用）；运行期不联网。
推理固定 eval 模式、CPU（可用 ``DEVICE`` 覆盖），输出 float32 供聚类，落盘可转 float16。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .common import DependencyUnavailable, resolve_weights_dir


class Embedder:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.model_dir = resolve_weights_dir() / cfg["model"]["relativePath"]
        required = [self.model_dir / "config.json", self.model_dir / "pytorch_model.bin"]
        missing = [path.name for path in required if not path.is_file()]
        if missing:
            raise DependencyUnavailable(
                f"模型权重缺失：{self.model_dir}（缺少 {', '.join(missing)}）"
            )
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - 镜像内必装
            raise DependencyUnavailable(f"transformers/torch 不可用：{exc}") from exc

        self.torch = torch
        self.device = str(cfg["model"].get("device") or "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
        self.model = AutoModel.from_pretrained(str(self.model_dir))
        self.model.eval()
        self.model.to(self.device)
        self.dimension = int(self.model.config.hidden_size)
        expected = int(cfg["model"]["dimension"])
        if self.dimension != expected:
            raise DependencyUnavailable(
                f"模型维度 {self.dimension} 与配置 {expected} 不一致"
            )

    def encode(self, texts: Sequence[str], batch_size: int | None = None) -> np.ndarray:
        """返回 L2 归一化后的 float32 向量矩阵 (N, D)。"""

        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        torch = self.torch
        size = int(batch_size or self.cfg["model"]["batchSize"])
        vectors: list[np.ndarray] = []
        with torch.inference_mode():
            for start in range(0, len(texts), size):
                batch = list(texts[start : start + size])
                encoded = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=int(self.cfg["model"]["maxTokens"]),
                    return_tensors="pt",
                )
                encoded = {key: value.to(self.device) for key, value in encoded.items()}
                output = self.model(**encoded)
                hidden = output.last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                summed = (hidden * mask).sum(dim=1)
                counts = mask.sum(dim=1).clamp(min=1e-6)
                pooled = (summed / counts).float().cpu().numpy()
                vectors.append(pooled)
        matrix = np.concatenate(vectors, axis=0).astype(np.float32)
        if self.cfg["model"].get("normalize", True):
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            matrix = matrix / np.clip(norms, 1e-12, None)
        return matrix

    @property
    def model_version(self) -> str:
        return str(self.cfg["model"]["name"])
