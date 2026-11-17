"""bge-base-zh-v1.5 文本向量（与 OP-03 同模型）。

来源：复制自 ``operator/dm-text-clustering/utils/embedder.py``（OP-03，0.1.0），
按任务书 2.1 允许复制小函数并注明来源。增加长文本分块均值接口。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from .common import DependencyUnavailable, resolve_device, resolve_weights_dir


class Embedder:
    def __init__(self, cfg: dict) -> None:
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
        except ImportError as exc:  # pragma: no cover
            raise DependencyUnavailable(f"transformers/torch 不可用：{exc}") from exc

        self.torch = torch
        self.device = resolve_device(cfg["model"].get("device"))
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
        self.model = AutoModel.from_pretrained(str(self.model_dir))
        self.model.eval()
        self.model.to(self.device)
        self.dimension = int(self.model.config.hidden_size)
        if self.dimension != int(cfg["model"]["dimension"]):
            raise DependencyUnavailable("模型维度与配置不一致")

    def encode(self, texts: Sequence[str], batch_size: int | None = None) -> np.ndarray:
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
                hidden = self.model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-6)
                vectors.append(pooled.float().cpu().numpy())
        matrix = np.concatenate(vectors, axis=0).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.clip(norms, 1e-12, None)

    def encode_document(self, text: str) -> np.ndarray:
        """长文本按 512 token 分块，均值后 L2 归一化。"""

        chunks = self._chunks(text)
        if not chunks:
            return np.zeros(self.dimension, dtype=np.float32)
        matrix = self.encode(chunks)
        averaged = matrix.mean(axis=0)
        return averaged / max(float(np.linalg.norm(averaged)), 1e-12)

    def _chunks(self, text: str) -> list[str]:
        max_tokens = int(self.cfg["model"]["maxTokens"])
        ids = self.tokenizer.encode(text or "", add_special_tokens=False)
        if not ids:
            return []
        return [
            self.tokenizer.decode(ids[start : start + max_tokens], skip_special_tokens=True)
            for start in range(0, len(ids), max_tokens)
        ]

    @property
    def model_version(self) -> str:
        return str(self.cfg["model"]["name"])
