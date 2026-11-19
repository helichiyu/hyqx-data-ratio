#!/usr/bin/env bash
# 生成最小 Docker 构建压缩包（S0-9）。
#
# 用法：
#   bash scripts/package_docker_bundle.sh --version 0.1.0
#   bash scripts/package_docker_bundle.sh --dry-run
#
# 输出：dist/op-data-mixing-<version>.tar.gz
# 内容：operator/ 下 Docker 构建与运行必需文件（allowlist 单一来源）。
# 压缩包解压到空目录后应可直接 docker build。

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTEXT="$ROOT/operator"
ALLOWLIST="$ROOT/scripts/bundle_allowlist.txt"
VERSION=""
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            [ $# -ge 2 ] || { echo "--version 缺少参数" >&2; exit 2; }
            VERSION="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            echo "未知参数：$1" >&2
            exit 2
            ;;
    esac
done

MAP_VERSION="$(sed -n 's/^[[:space:]]*"version": "\([^"]*\)".*/\1/p' "$CONTEXT/map.json" | head -n 1)"
if [ -z "$VERSION" ]; then
    VERSION="$MAP_VERSION"
fi
if [ "$VERSION" != "$MAP_VERSION" ]; then
    echo "版本不一致：--version=$VERSION 与 map.json=$MAP_VERSION" >&2
    exit 1
fi

STAGE="$ROOT/dist/.stage-$VERSION-$$"
rm -rf "$STAGE"
mkdir -p "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

echo "构建上下文：$CONTEXT"
echo "版本：$VERSION"
(
    cd "$CONTEXT"
    while IFS= read -r line; do
        line="$(printf '%s' "$line" | sed 's/#.*//' | sed 's/[[:space:]]*$//')"
        [ -z "$line" ] && continue
        # shellcheck disable=SC2086
        for match in $line; do
            if [ -e "$match" ]; then
                cp -a --parents "$match" "$STAGE"/
            fi
        done
    done < "$ALLOWLIST"
)

# 清理 Python 缓存（后续 utils/ 下会产生 __pycache__）
find "$STAGE" -name '*.pyc' -delete
find "$STAGE" -depth -type d -name '__pycache__' -empty -delete
# 权重目录的 README 属于仓库说明，不进入运行时压缩包
find "$STAGE/weights" -name '*.md' -delete 2>/dev/null || true

for required in Dockerfile .dockerignore docker-compose.yml inference.py requirements.txt map.json \
                baseline/tree-snapshot.json baseline/source-map.json baseline/thresholds.json; do
    if [ ! -f "$STAGE/$required" ]; then
        echo "缺少必需文件：$required" >&2
        exit 1
    fi
done

CORE_COUNT="$(find "$STAGE" -mindepth 2 -maxdepth 2 -name core.py | wc -l | tr -d ' ')"
if [ "$CORE_COUNT" != "22" ]; then
    echo "算子核心数量应为 22，实际 $CORE_COUNT" >&2
    exit 1
fi
if [ -d "$STAGE/_template" ]; then
    echo "压缩包不应包含 _template" >&2
    exit 1
fi

FORBIDDEN="$(find "$STAGE" \( -name tests -o -name dataset -o -name output -o -name __pycache__ \
    -o -name '*.pyc' -o -name '*.md' -o -name '.git' -o -name '.env' \) -print)"
if [ -n "$FORBIDDEN" ]; then
    echo "压缩包含非运行文件：" >&2
    echo "$FORBIDDEN" >&2
    exit 1
fi

if [ "$DRY_RUN" = "1" ]; then
    echo "dry-run 文件清单："
    (cd "$STAGE" && find . -type f | sed 's#^\./##' | sort)
    echo "dry-run 通过：算子核心文件齐全，无测试/样例/证据/文档"
    exit 0
fi

mkdir -p "$ROOT/dist"
BUNDLE="$ROOT/dist/op-data-mixing-$VERSION.tar.gz"
tar -czf "$BUNDLE" -C "$STAGE" .

if tar -tzf "$BUNDLE" | grep -Eq '(^|/)(tests|dataset|output)/|\.md$|\.pyc$|__pycache__|(^|/)\.git/|(^|/)\.env$'; then
    echo "压缩包清单异常：含非运行文件" >&2
    exit 1
fi
TAR_CORE_COUNT="$(tar -tzf "$BUNDLE" | grep -c '/core\.py$' || true)"
if [ "$TAR_CORE_COUNT" != "22" ]; then
    echo "压缩包内算子核心应为 22，实际 $TAR_CORE_COUNT" >&2
    exit 1
fi

echo "已生成：$BUNDLE"
echo "大小：$(wc -c < "$BUNDLE" | tr -d ' ') 字节"
echo "SHA-256：$(sha256sum "$BUNDLE" | awk '{print $1}')"
echo "文件数：$(tar -tzf "$BUNDLE" | wc -l | tr -d ' ')"
