"""OP-01 公共工具：配置加载、指纹、时间、zip 安全展开、产物写出。

来源：S0 模板 + 根 ``inference.py`` 的路径/指纹约定（2026-11-16）；算子内只使用
相对导入，禁止依赖 FastAPI/HTTP。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .hashes import file_hashes

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


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ts_to_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )


def ts_to_dt(timestamp: float) -> str:
    """分区 dt：本地日期 YYYY-MM-DD（与文件时间口径一致）。"""

    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


def params_hash(params: dict[str, Any] | None) -> str:
    canonical = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_input(
    root: Path, members: Iterable[tuple[str, Path]]
) -> tuple[str, int]:
    """按根输入类型选择指纹算法，尽量与根 ``inference.py`` 的 runId 口径一致。

    - 单文件（非 zip）：``file\\0大小\\0sha256``；
    - 目录/zip：成员相对路径 + 大小 + 内容哈希聚合（zip 与 HTTP 层按压缩包计算不同，
      已在输入清单中说明）。
    """

    if root.is_file() and root.suffix.lower() != ".zip":
        _, sha256 = file_hashes(root)
        digest = hashlib.sha256()
        digest.update(b"file\0")
        digest.update(str(root.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii"))
        return digest.hexdigest(), root.stat().st_size
    return fingerprint_members(members)


def fingerprint_members(members: Iterable[tuple[str, Path]]) -> tuple[str, int]:
    """输入指纹：成员相对路径 + 大小 + 内容 SHA-256 排序聚合；返回 (sha256, 总字节)。

    与根 ``inference.py`` 对目录输入的算法一致；对 zip 输入，HTTP 层指纹按压缩包
    计算，本算子按展开后的成员计算，差异在 manifest notes 中说明。
    """

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


def compute_run_id(fingerprint: str, version: str, param_digest: str, seed: int) -> str:
    return hashlib.sha256(
        f"{fingerprint}|{version}|{param_digest}|{seed}".encode("utf-8")
    ).hexdigest()[:16]


def ensure_output_dir(output_dir: str | Path | None, fallback: str = "runtime/output") -> Path:
    target = Path(output_dir or fallback).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def safe_extract_zip(
    archive_path: Path,
    destination: Path,
    allowed_suffixes: set[str],
    *,
    max_members: int,
    max_bytes: int,
) -> tuple[list[Path], list[str]]:
    """防御性 zip 展开：只取 basename、白名单后缀、限制成员数/解压总量、跳过符号链接。"""

    extracted: list[Path] = []
    skipped: list[str] = []
    seen: set[str] = set()
    total = 0
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > max_members:
            raise ValueError(f"zip 成员数超过上限 {max_members}")
        for member in members:
            name = Path(member.filename.replace("\\", "/")).name
            if member.is_dir() or not name:
                continue
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                skipped.append(f"{name}（符号链接）")
                continue
            if Path(name).suffix.lower() not in allowed_suffixes:
                skipped.append(f"{name}（后缀不在白名单）")
                continue
            if name in seen:
                skipped.append(f"{name}（重名，保留第一个）")
                continue
            seen.add(name)
            total += member.file_size
            if total > max_bytes:
                raise ValueError(f"zip 解压总量超过上限 {max_bytes} 字节")
            target = destination / name
            with target.open("wb") as sink, archive.open(member) as source:
                shutil.copyfileobj(source, sink, CHUNK)
            extracted.append(target)
    return extracted, skipped


def safe_file_name(raw: str | None, fallback: str = "file") -> str:
    name = Path(str(raw or "").replace("\\", "/")).name
    name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127).strip()
    return name or fallback


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
