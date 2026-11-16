"""标准产物写出：Parquet(zstd)、WebP、16 kHz mono WAV、H.264 MP4。

ffmpeg 探测/调用逻辑复制自 ``operator/dm-multimodal-analysis/utils/media.py``（OP-01，
版本 0.1.0），按任务书 2.1 允许复制小函数并注明来源。
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

PARQUET_SCHEMA = pa.schema(
    [
        ("record_id", pa.string()),
        ("modal", pa.string()),
        ("source", pa.string()),
        ("dt", pa.string()),
        ("text", pa.string()),
        ("text_chars", pa.int64()),
        ("text_sha256", pa.string()),
        ("format", pa.string()),
        ("size_bytes", pa.int64()),
        ("md5", pa.string()),
        ("sha256", pa.string()),
        ("simhash", pa.string()),
        ("phash", pa.string()),
        ("standard_path", pa.string()),
        ("duplicate_of", pa.string()),
        ("quality_json", pa.string()),
        ("metadata_json", pa.string()),
    ]
)


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    candidate = shutil.which("ffmpeg")
    if not candidate:
        try:
            import imageio_ffmpeg  # type: ignore

            candidate = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("ffmpeg 不可用") from exc
    return candidate


@lru_cache(maxsize=8)
def has_encoder(name: str) -> bool:
    result = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-encoders"],
        capture_output=True, timeout=60, check=False,
    )
    return name in result.stdout.decode("utf-8", errors="replace")


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout, check=False)


def write_parquet(
    rows: list[dict[str, Any]], path: Path, *, row_group_size: int, compression: str,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda item: item["record_id"])
    table = pa.Table.from_pylist(ordered, schema=PARQUET_SCHEMA)
    pq.write_table(
        table,
        path,
        compression=compression,
        row_group_size=row_group_size,
        use_dictionary=True,
        write_statistics=True,
    )
    return table.num_rows


def read_parquet_rows(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist()


def standardize_image(
    source: Path, destination: Path, cfg: dict[str, Any]
) -> tuple[Path, list[str]]:
    from PIL import Image

    notes: list[str] = []
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.mode else "RGB")
            notes.append("IMAGE_MODE_CONVERTED")
        image.save(
            destination,
            format="WEBP",
            quality=int(cfg["formats"]["image"]["quality"]),
            method=int(cfg["formats"]["image"]["method"]),
        )
    if destination.suffix.lower() != ".webp":
        notes.append("IMAGE_CONTAINER_NOT_WEBP")
    return destination, notes


def standardize_audio(
    source: Path, destination: Path, cfg: dict[str, Any], timeout: int
) -> tuple[Path, list[str]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    audio = cfg["formats"]["audio"]
    command = [
        ffmpeg_exe(), "-y", "-v", "error", "-i", str(source),
        "-vn", "-ac", str(int(audio["channels"])), "-ar", str(int(audio["sampleRate"])),
        "-c:a", str(audio["codec"]), str(destination),
    ]
    completed = _run(command, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace")[-800:])
    return destination, ["AUDIO_16K_MONO"]


def standardize_video(
    source: Path, destination: Path, cfg: dict[str, Any], timeout: int
) -> tuple[Path, list[str]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    video = cfg["formats"]["video"]
    notes: list[str] = []
    if has_encoder("libx264"):
        command = [
            ffmpeg_exe(), "-y", "-v", "error", "-i", str(source),
            "-c:v", "libx264", "-preset", str(video["preset"]), "-crf", str(video["crf"]),
            "-pix_fmt", "yuv420p", "-c:a", str(video["audioCodec"]), "-b:a", "128k",
            "-movflags", "+faststart", "-f", "mp4", str(destination),
        ]
        completed = _run(command, timeout=timeout)
        if completed.returncode == 0:
            return destination, ["VIDEO_H264_TRANSCODED"]
        notes.append("VIDEO_TRANSCODE_FAILED")
    else:
        notes.append("VIDEO_TRANSCODE_UNAVAILABLE")

    remux = [
        ffmpeg_exe(), "-y", "-v", "error", "-i", str(source),
        "-c", "copy", "-movflags", "+faststart", "-f", "mp4", str(destination),
    ]
    completed = _run(remux, timeout=timeout)
    if completed.returncode == 0:
        notes.append("VIDEO_REMUXED_WITHOUT_TRANSCODE")
        return destination, notes

    fallback = destination.with_suffix(source.suffix or ".bin")
    shutil.copyfile(source, fallback)
    notes.append("VIDEO_COPIED_ORIGINAL")
    return fallback, notes


def mean_brightness(path: Path) -> float | None:
    from PIL import Image

    try:
        with Image.open(path) as image:
            gray = image.convert("L").resize((32, 32))
            return round(float(np.asarray(gray, dtype=np.float64).mean()), 3)
    except Exception:  # noqa: BLE001 - 黑帧检测失败不阻塞
        return None
