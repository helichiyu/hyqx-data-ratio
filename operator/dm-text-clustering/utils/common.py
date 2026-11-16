"""OP-03 公共工具：配置、路径、JSON/npy 写出、指纹。

来源：S0 模板与 OP-01 ``utils/common.py``（0.1.0）的精简版；按任务书 2.1 允许复制
小函数并注明来源，不跨算子 import。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PACKAGE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_DIR / "configs"
OPERATOR_ROOT = PACKAGE_DIR.parent


class DependencyUnavailable(RuntimeError):
    """模型/权重不可用。"""


def load_config(name: str = "cluster.json") -> dict[str, Any]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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


def resolve_weights_dir() -> Path:
    configured = os.getenv("WEIGHTS_DIR")
    if configured:
        return Path(configured).resolve()
    return OPERATOR_ROOT / "weights"
