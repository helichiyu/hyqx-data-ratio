# 数据配比中心 · 22 个算子单镜像（唯一生产镜像，唯一 HTTP 入口）
#
# 构建（仓库根 = 唯一构建上下文）：
#   docker build -t op-data-mixing:0.1.0 .
# 运行：
#   docker compose up -d
#   curl http://localhost:17025/dm-multimodal-analysis/healthz
#
# 22 个算子共用本镜像与容器，不按算子拆镜像、不按算子另起端口。

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    INPUT_DIR=/app/runtime/transport/input \
    OUTPUT_DIR=/app/runtime/transport/output \
    PORT=17025

WORKDIR /app

# 解码/探测依赖：ffmpeg（含 ffprobe）、libmagic（模态判定）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# 构建上下文 = operator/ 目录；.dockerignore 用 allowlist 控制实际内容
COPY . /app/

# 权重校验：SHA256SUMS 非空时逐项校验（权重本身不进 git）
RUN if [ -s /app/weights/SHA256SUMS ]; then cd /app/weights && sha256sum -c SHA256SUMS; fi

# 构建期自检：注册表 22 条、22 个算子包可导入、根入口可加载
RUN python - <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
ops = json.loads(Path("/app/map.json").read_text(encoding="utf-8"))["operators"]
assert len(ops) == 22, f"map.json 应为 22 条，实际 {len(ops)}"

import inference  # noqa: E402

app = inference.app
health = {route.path for route in app.routes if route.path.endswith("/healthz")}
assert len(health - {"/healthz"}) == 22, health
print("image self-check ok: 22 operators registered")
PY

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --no-create-home appuser \
    && mkdir -p /app/runtime/transport/input /app/runtime/transport/output \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 17025

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:17025/health', timeout=3).read()"

CMD ["uvicorn", "inference:app", "--host", "0.0.0.0", "--port", "17025", "--workers", "1"]
