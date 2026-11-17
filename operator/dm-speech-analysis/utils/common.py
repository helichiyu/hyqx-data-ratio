""" OP-11 公共工具：配置、路径、JSON 写出、指纹、记录读取。

来源：OP-03 ``utils/common.py``（0.1.0）的精简版；按任务书 2.1 允许复制小函数并
注明来源，不跨算子 import。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PACKAGE_DIR = Path(__file__).resolve().parents[1]
OPERATOR_ROOT = PACKAGE_DIR.parent


class DependencyUnavailable(RuntimeError):
    """模型/权重不可用。"""


def resolve_weights_dir() -> Path:
    """权重根：``WEIGHTS_DIR`` > 本机模型仓（``D:/models``、``/models``）> 镜像内 weights。"""

    configured = os.getenv("WEIGHTS_DIR")
    if configured:
        return Path(configured).resolve()
    for candidate in (Path("D:/models"), Path("/models")):
        if (candidate / "shared").is_dir():
            return candidate.resolve()
    return OPERATOR_ROOT / "weights"
CONFIG_DIR = PACKAGE_DIR / "configs"
RECORD_REQUIRED = ("record_id", "modal", "source", "metadata", "quality", "partitions", "hashes")


def load_config(name: str = "speech.json") -> dict[str, Any]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8", newline="\n") as sink:
        for row in rows:
            sink.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def file_hashes(path: str | Path) -> tuple[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def params_hash(params: dict[str, Any] | None) -> str:
    canonical = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_file(path: Path) -> tuple[str, int]:
    _, sha256 = file_hashes(path)
    digest = hashlib.sha256()
    digest.update(b"file\0")
    digest.update(str(path.stat().st_size).encode("ascii"))
    digest.update(b"\0")
    digest.update(sha256.encode("ascii"))
    return digest.hexdigest(), path.stat().st_size


def ensure_output_dir(output_dir: str | Path | None) -> Path:
    target = Path(output_dir or "runtime/output").resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resolve_relative(raw: str | Path) -> Path:
    """把 ``baseline/...`` 之类的相对路径解析到 ``operator/`` 根。"""

    path = Path(raw)
    return path if path.is_absolute() else (OPERATOR_ROOT / path)


def locate_records(input_path: str) -> tuple[Path, Path]:
    root = Path(input_path).resolve()
    if root.is_file():
        if root.suffix.lower() != ".jsonl":
            raise ValueError(f"只接受 .jsonl 记录文件，实际 {root.name}")
        return root, root.parent
    for candidate in (
        root / "records.jsonl",
        root / "output" / "records.jsonl",
        root / "result.jsonl",
    ):
        if candidate.is_file():
            return candidate, candidate.parent
    matches = sorted(root.glob("*.jsonl"))
    if matches:
        return matches[0], matches[0].parent
    raise FileNotFoundError(f"目录中没有 records.jsonl：{root}")


def ensure_under_roots(raw: str, roots: Iterable[Path]) -> Path:
    """参数路径闸门：与 HTTP 层同口径，只允许 INPUT_DIR / OUTPUT_DIR 内路径。"""

    target = Path(raw).resolve()
    for root in roots:
        root_resolved = Path(root).resolve()
        if target == root_resolved or root_resolved in target.parents:
            return target
    raise ValueError(f"路径不在允许的根目录内：{target}")


def environment_roots() -> list[Path]:
    return [
        Path(os.getenv("INPUT_DIR", OPERATOR_ROOT / "runtime" / "input")),
        Path(os.getenv("OUTPUT_DIR", OPERATOR_ROOT / "runtime" / "output")),
    ]


def percentile_nearest_rank(values: list[float], p: float) -> float | None:
    """最近秩分位数（nearest-rank），口径写入 README，避免插值口径漂移。"""

    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return float(ordered[rank - 1])


def cuda_available() -> bool:
    """CUDA 是否可用；torch 缺失或初始化失败时返回 ``False``。"""

    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 - 探针与回落场景不因 torch 异常中断
        return False


def resolve_device(configured: Any = None) -> str:
    """解析推理设备：``DEVICE`` 环境变量 > 算子配置 > ``auto``。

    ``auto`` 在 CUDA 可用时使用 ``cuda:0``，否则回落 ``cpu``；显式指定
    ``cuda`` 但 CUDA 不可用时同样回落，保证无 GPU 节点也能启动。
    """

    requested = str(os.getenv("DEVICE") or configured or "auto").strip().lower()
    if requested not in {"cpu", "auto"} and not requested.startswith("cuda"):
        requested = "auto"
    if requested == "auto":
        return "cuda:0" if cuda_available() else "cpu"
    if requested.startswith("cuda") and not cuda_available():
        return "cpu"
    return requested
