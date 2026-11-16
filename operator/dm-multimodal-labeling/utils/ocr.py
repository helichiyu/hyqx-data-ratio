"""RapidOCR（PP-OCR ONNX）图像文字识别。

RapidOCR 1.4.4，Apache-2.0；模型随 wheel 打包，运行期不联网。
返回按阅读顺序排序的文本与逐条置信度，供打标证据使用；失败返回明确异常。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import DependencyUnavailable

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - 镜像内必装
            raise DependencyUnavailable(f"RapidOCR 不可用：{exc}") from exc
        _ENGINE = RapidOCR()
    return _ENGINE


class OcrFailed(RuntimeError):
    """OCR 执行失败。"""


def ocr_image(path: str | Path) -> dict[str, Any]:
    result, _ = _engine()(str(path))
    if not result:
        return {"text": "", "items": [], "chars": 0}
    items = []
    for box, text, score in result:
        text = str(text).strip()
        if not text:
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        items.append(
            {
                "text": text,
                "score": round(float(score), 6),
                "x": round(min(xs), 2),
                "y": round(min(ys), 2),
                "width": round(max(xs) - min(xs), 2),
                "height": round(max(ys) - min(ys), 2),
            }
        )
    items.sort(key=lambda item: (round(item["y"] / 10), item["x"]))
    text = "\n".join(item["text"] for item in items)
    return {"text": text, "items": items, "chars": len(text)}
