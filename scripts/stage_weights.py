"""构建镜像前，把模型仓的 shared/ 权重暂存到 operator/weights/。

镜像构建上下文是 ``operator/``，权重不进 git；Dockerfile 构建期按
``SHA256SUMS`` 逐项校验，缺文件即构建失败。本脚本在构建前完成暂存与校验：

    python scripts/stage_weights.py            # 暂存 + 校验
    python scripts/stage_weights.py --clean    # 构建完成后清理，仓库恢复为仅清单

模型仓解析顺序与算子一致：``WEIGHTS_DIR`` > ``D:\\models`` / ``/models``
（需含 ``shared/``）> ``operator/weights``（已暂存时跳过拷贝）。
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DIR = REPO_ROOT / "operator"
WEIGHTS_DIR = OPERATOR_DIR / "weights"
SUMS_FILE = WEIGHTS_DIR / "SHA256SUMS"
CHUNK = 1024 * 1024


def _model_store() -> Path | None:
    import os

    configured = os.getenv("WEIGHTS_DIR")
    if configured and (Path(configured) / "shared").is_dir():
        return Path(configured)
    for candidate in (Path("D:/models"), Path("/models")):
        if (candidate / "shared").is_dir():
            return candidate
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify() -> int:
    """按 SHA256SUMS 校验 weights/ 下所有条目，返回失败数。"""

    failures = 0
    for line in SUMS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        expected, _, relative = line.partition(" ")
        relative = relative.lstrip("*").strip()
        target = WEIGHTS_DIR / relative
        if not target.is_file():
            print(f"MISSING {relative}")
            failures += 1
            continue
        actual = _sha256(target)
        if actual != expected:
            print(f"MISMATCH {relative}: {actual} != {expected}")
            failures += 1
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true",
                        help="删除 operator/weights/shared（构建完成后恢复仓库仅清单状态）")
    args = parser.parse_args()

    if args.clean:
        shutil.rmtree(WEIGHTS_DIR / "shared", ignore_errors=True)
        print("已清理 operator/weights/shared（SHA256SUMS 与 .gitkeep 保留）")
        return 0

    if not SUMS_FILE.is_file():
        print(f"缺少 {SUMS_FILE}")
        return 2

    staged_shared = WEIGHTS_DIR / "shared"
    store = _model_store()
    if store is None or store == WEIGHTS_DIR:
        if staged_shared.is_dir() and any(staged_shared.iterdir()):
            print("operator/weights/shared 已有内容，跳过拷贝，直接校验")
        else:
            print("未找到模型仓（WEIGHTS_DIR / D:\\models / /models，需含 shared/），且 operator/weights/shared 为空")
            return 2
    else:
        source = store / "shared"
        staged_shared.mkdir(parents=True, exist_ok=True)
        for item in sorted(source.iterdir()):
            destination = staged_shared / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)
            print(f"staged shared/{item.name}")

    failures = _verify()
    if failures:
        print(f"校验失败 {failures} 项，禁止构建镜像")
        return 1
    print("SHA256SUMS 校验通过，可以 docker compose up -d --build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
