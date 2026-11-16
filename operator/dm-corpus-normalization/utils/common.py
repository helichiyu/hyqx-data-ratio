"""OP-02 公共工具：配置、哈希、指纹、JSON 写出。

来源：复制自 ``operator/dm-multimodal-analysis/utils/common.py``（OP-01，版本 0.1.0），
按任务书 2.1「允许复制小型工具函数并注明来源」；不跨算子 import。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

PACKAGE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_DIR / "configs"
CHUNK = 1024 * 1024


def load_config(name: str) -> dict[str, Any]:
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
        while True:
            chunk = source.read(CHUNK)
            if not chunk:
                break
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


def fingerprint_members(members: Iterable[tuple[str, Path]]) -> tuple[str, int]:
    digest = hashlib.sha256()
    digest.update(b"dir\0")
    total = 0
    for relative, path in sorted(members, key=lambda item: item[0]):
        size = path.stat().st_size
        total += size
        _, sha256 = file_hashes(path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest(), total


def ensure_output_dir(output_dir: str | Path | None, fallback: str = "runtime/output") -> Path:
    target = Path(output_dir or fallback).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def relative_posix(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
