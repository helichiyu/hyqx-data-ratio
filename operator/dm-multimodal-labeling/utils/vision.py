"""视频关键帧抽取（ffmpeg，真实 pts）。

来源：复制自 ``operator/dm-multimodal-analysis/utils/media.py``（OP-01，0.1.0）的抽帧
逻辑，按任务书 2.1 允许复制小函数并注明来源。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_PTS_RE = re.compile(r"pts_time:(?P<pts>[0-9.]+)")


class VisionFailed(RuntimeError):
    """抽帧失败。"""


def extract_keyframes(
    video: Path,
    out_dir: Path,
    *,
    max_frames: int,
    duration_sec: float | None,
    timeout: int,
) -> list[dict[str, Any]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VisionFailed("ffmpeg 不可用")
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.jpg"):
        stale.unlink()
    duration = duration_sec or 0
    if duration > 0:
        rate = max_frames / duration
        filter_expr = f"fps={rate:.6f},showinfo"
    else:
        filter_expr = f"select=not(mod(n\\,{max(1, 30 // max_frames)})),showinfo"
    completed = subprocess.run(
        [
            ffmpeg, "-y", "-v", "info", "-i", str(video),
            "-vf", filter_expr, "-fps_mode", "vfr", "-q:v", "3",
            str(out_dir / "frame_%04d.jpg"),
        ],
        capture_output=True, timeout=timeout, check=False,
    )
    if completed.returncode != 0:
        raise VisionFailed(
            completed.stderr.decode("utf-8", errors="replace")[-600:]
        )
    timestamps = [float(item) for item in _PTS_RE.findall(
        completed.stderr.decode("utf-8", errors="replace")
    )]
    frames = sorted(out_dir.glob("frame_*.jpg"))[:max_frames]
    return [
        {
            "index": index,
            "tsSec": round(timestamps[index], 3) if index < len(timestamps) else None,
            "path": frame,
        }
        for index, frame in enumerate(frames)
    ]
