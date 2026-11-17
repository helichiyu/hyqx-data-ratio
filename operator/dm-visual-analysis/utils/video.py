"""视频属性：镜头切换、平均镜头时长、光流动态/静态占比、关键帧时间。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def _hist(frame) -> np.ndarray:
    import cv2

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def analyze(path: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    import cv2

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"视频不可解码：{path}")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        sample_fps = float(cfg["video"]["sampleFps"])
        max_frames = int(cfg["video"]["maxFrames"])
        step = max(1, int(round(fps / sample_fps))) if fps > 0 else 1

        cuts: list[float] = []
        flows: list[float] = []
        previous_hist = None
        previous_gray = None
        sampled = 0
        shot_correlation = float(cfg["video"]["shotHistCorrelation"])
        flow_threshold = float(cfg["video"]["flowMagnitudeThreshold"])
        index = 0
        while sampled < max_frames:
            if not capture.grab():
                break
            if index % step == 0:
                ok, frame = capture.retrieve()
                if not ok:
                    index += 1
                    continue
                timestamp = index / fps if fps > 0 else float(index)
                hist = _hist(frame)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if previous_hist is not None:
                    correlation = float(cv2.compareHist(previous_hist, hist, cv2.HISTCMP_CORREL))
                    if correlation < shot_correlation:
                        cuts.append(round(timestamp, 6))
                if previous_gray is not None:
                    flow = cv2.calcOpticalFlowFarneback(
                        previous_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
                    )
                    magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                    flows.append(float(magnitude.mean()))
                previous_hist = hist
                previous_gray = gray
                sampled += 1
            index += 1

        duration = (index / fps) if fps > 0 else 0.0
        shots = len(cuts) + 1 if sampled else 0
        dynamic = sum(1 for value in flows if value > flow_threshold)
        return {
            "fps": round(fps, 6),
            "frameCount": total,
            "width": width,
            "height": height,
            "durationSec": round(duration, 6),
            "sampledFrames": sampled,
            "shots": shots,
            "cutTimesSec": cuts[:200],
            "meanShotDurationSec": (
                round(duration / shots, 6) if shots else None
            ),
            "flowSamples": len(flows),
            "flowMeanMagnitude": round(float(np.mean(flows)), 6) if flows else None,
            "dynamicFrameRatio": round(dynamic / len(flows), 6) if flows else None,
            "staticFrameRatio": round(1 - dynamic / len(flows), 6) if flows else None,
            "actionCoverage": {
                "status": "unavailable",
                "reasonCode": cfg["unavailable"]["action"],
            },
            "audioVisualBleu": {
                "status": "unavailable",
                "reasonCode": cfg["unavailable"]["audioVisualBleu"],
            },
        }
    finally:
        capture.release()
