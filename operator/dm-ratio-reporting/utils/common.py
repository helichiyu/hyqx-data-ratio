"""OP-19 公共工具：配置、路径、JSON、哈希与输入指纹。

来源：OP-17 ``utils/common.py``（0.1.0）的复制精简版；按任务书 2.1 允许复制
小型工具函数并注明来源，不跨算子 import。
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


def load_config(name: str = "reporting.json") -> dict[str, Any]:
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


def fingerprint_path(path: str | Path) -> str:
    """与 HTTP 层 ``inference._fingerprint`` 同口径；保证 manifest.runId 与目录名一致。"""

    target = Path(path).resolve()
    digest = hashlib.sha256()
    if target.is_dir():
        digest.update(b"dir\0")
        for item in sorted(target.rglob("*"), key=lambda p: p.relative_to(target).as_posix()):
            relative = item.relative_to(target).as_posix()
            if item.is_symlink():
                raise ValueError(f"输入目录包含符号链接，拒绝处理：{relative}")
            if not item.is_file():
                continue
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(item.stat().st_size).encode("ascii"))
            digest.update(b"\0")
            digest.update(file_hashes(item)[1].encode("ascii"))
            digest.update(b"\0")
    elif target.is_file():
        digest.update(b"file\0")
        digest.update(str(target.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_hashes(target)[1].encode("ascii"))
    else:
        raise FileNotFoundError(str(target))
    return digest.hexdigest()


def ensure_output_dir(output_dir: str | Path | None) -> Path:
    target = Path(output_dir or "runtime/output").resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resolve_relative(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (OPERATOR_ROOT / path)


def ensure_under_roots(raw: str, roots: Iterable[Path]) -> Path:
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
