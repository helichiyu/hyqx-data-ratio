"""OP-12 单测与端到端：图像熵/清晰度/主色、视频镜头/光流、边界与真实媒体。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from op12_env import CORE, OP02_EVIDENCE

cfg = CORE.load_config()
image_util = CORE.image_util
video_util = CORE.video_util


def test_image_entropy_and_dominant_color(tmp_path: Path):
    from PIL import Image

    solid = tmp_path / "solid.png"
    Image.new("RGB", (64, 64), (255, 0, 0)).save(solid)
    stats = image_util.analyze(solid, cfg)
    assert stats["entropy"] == 0.0
    assert stats["sharpnessLaplacian"] == 0.0
    assert stats["dominantColors"][0]["hex"] == "#ff0000"
    assert stats["scene"]["status"] == "unavailable"

    rng = np.random.default_rng(42)
    noise = (rng.random((64, 64, 3)) * 255).astype("uint8")
    noisy = tmp_path / "noise.png"
    Image.fromarray(noise).save(noisy)
    stats = image_util.analyze(noisy, cfg)
    assert stats["entropy"] > 5.0
    assert stats["sharpnessLaplacian"] > 100


def test_video_shots_and_flow(tmp_path: Path):
    import cv2

    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 64))
    for index in range(30):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        if index < 15:
            frame[:] = (0, 0, 255)
        else:
            frame[:] = (0, 255, 0)
        if index % 2:
            frame[10:40, 10:40] = (255, 255, 255)
        writer.write(frame)
    writer.release()

    stats = video_util.analyze(path, cfg)
    assert stats["fps"] > 0
    assert stats["shots"] >= 2
    assert stats["cutTimesSec"]
    assert stats["dynamicFrameRatio"] is not None
    assert stats["actionCoverage"]["status"] == "unavailable"


def _record(record_id: str, modal: str) -> dict:
    return {
        "record_id": record_id,
        "modal": modal,
        "source": "web_text",
        "text": None,
        "metadata": {"format": "webp" if modal == "image" else "mp4", "sizeBytes": 100},
        "quality": {"completeness": 1.0, "decodable": True, "emptyText": True},
        "partitions": {"modal": modal, "source": "web_text", "dt": "2026-11-16"},
        "hashes": {"md5": None, "sha256": None, "simhash": None, "phash": None},
    }


def test_core_image_and_missing_media(tmp_path: Path):
    from PIL import Image

    input_dir = tmp_path / "input"
    (input_dir / "standard" / "images").mkdir(parents=True)
    Image.new("RGB", (32, 32), (0, 128, 255)).save(input_dir / "standard" / "images" / "r1.webp")
    (input_dir / "records.jsonl").write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in (_record("r1", "image"), _record("r404", "image"))
        )
        + "\n",
        encoding="utf-8",
    )
    result = CORE.run(str(input_dir), {}, 42, str(tmp_path / "out"))
    metrics = result["metrics"]
    assert metrics["mediaCounts"] == {"image": 2}
    assert metrics["processedRecords"] == 1
    assert metrics["failuresByReason"] == {"STANDARD_MEDIA_MISSING": 1}
    assert metrics["image"]["entropyMean"] == 0.0


def test_core_real_media(tmp_path: Path):
    if not (OP02_EVIDENCE / "standard" / "images").is_dir():
        import pytest

        pytest.skip("缺少 OP-02 标准媒体")
    result = CORE.run(str(OP02_EVIDENCE), {}, 42, str(tmp_path / "real"))
    metrics = result["metrics"]
    assert metrics["mediaCounts"] == {"image": 1, "video": 2}
    assert metrics["processedRecords"] >= 2
    assert metrics["image"]["entropyMean"] is not None
    assert metrics["video"]["dynamicFrameRatioMean"] is not None
