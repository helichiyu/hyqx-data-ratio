"""图像属性：香农熵、清晰度、亮度/对比度、色彩丰富度、主色。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def analyze(path: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    import cv2
    from PIL import Image

    try:
        with Image.open(path) as opened:
            rgb = np.asarray(opened.convert("RGB"))
    except Exception as exc:  # noqa: BLE001 - 解码失败统一报错
        raise ValueError(f"图像不可解码：{path}") from exc
    image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    bins = int(cfg["image"]["histogramBins"])
    histogram = np.bincount(gray.ravel(), minlength=bins).astype(np.float64)
    probabilities = histogram / histogram.sum()
    probabilities = probabilities[probabilities > 0]
    entropy = float(-(probabilities * np.log2(probabilities)).sum())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    b, g, r = cv2.split(image.astype(np.float32))
    rg = np.abs(r - g)
    yb = np.abs(0.5 * (r + g) - b)
    colorfulness = float(
        np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    )
    return {
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "entropy": round(entropy, 6),
        "sharpnessLaplacian": round(sharpness, 6),
        "brightnessMean": round(float(gray.mean()) / 255.0, 6),
        "contrastStd": round(float(gray.std()) / 255.0, 6),
        "colorfulness": round(colorfulness, 6),
        "dominantColors": _dominant_colors(image, int(cfg["image"]["dominantColors"])),
        "scene": {"status": "unavailable", "reasonCode": cfg["unavailable"]["scene"]},
        "objects": {"status": "unavailable", "reasonCode": cfg["unavailable"]["object"]},
    }


def _dominant_colors(image: np.ndarray, count: int) -> list[dict[str, Any]]:
    from PIL import Image

    rgb = Image.fromarray(image[:, :, ::-1])
    quantized = rgb.convert("P", palette=Image.ADAPTIVE, colors=count)
    palette = quantized.getpalette() or []
    total = float(image.shape[0] * image.shape[1])
    colors = quantized.getcolors(maxcolors=1 << 20) or []
    result = []
    for amount, index in sorted(colors, reverse=True)[:count]:
        base = index * 3
        if base + 2 >= len(palette):
            continue
        result.append(
            {
                "hex": "#%02x%02x%02x" % (palette[base], palette[base + 1], palette[base + 2]),
                "share": round(amount / total, 6),
            }
        )
    return result
