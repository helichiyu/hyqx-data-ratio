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
    PORT=17025 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /app

# 解码/探测依赖：ffmpeg、libmagic、OpenCV 运行库（RapidOCR）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libmagic1 libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# CUDA 兼容闸门：生产驱动为 12.4，镜像内 torch 的 CUDA runtime 不得高于该上限。
# 上限通过构建参数覆盖，版本号只在构建参数中出现一次；构建机无需 GPU。
ARG MAX_CUDA_RUNTIME=12.4
RUN MAX_CUDA_RUNTIME=${MAX_CUDA_RUNTIME} python - <<'PY'
import os

import torch

limit = tuple(int(part) for part in os.environ["MAX_CUDA_RUNTIME"].split("."))
runtime = torch.version.cuda
assert runtime is not None, "生产镜像必须包含 CUDA 版 torch（PyPI 默认 wheel 应为 cu124）"
current = tuple(int(part) for part in runtime.split("."))
assert current <= limit, f"torch CUDA runtime {runtime} 高于上限 {limit}"
print(f"torch {torch.__version__} cuda runtime {runtime} <= {limit[0]}.{limit[1]}")
PY

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

# 固定环境变量默认值直接写进镜像（团队约定，参考 docs/参考记录/anomalypattern.yaml）；
# 可变项——网关地址、密钥、后端切换、DEVICE——由部署时注入：docker compose 环境变量，
# 或 K8s Deployment env 按 "- name: / value:" 格式依次添加（密钥走 secretKeyRef）。
# 放在重层之后：调整这里的默认值不会使 apt/pip 层失效。
ENV MODEL_BACKEND=idg \
    MODEL_APP_ID=audioasr \
    SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1

USER appuser
EXPOSE 17025

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:17025/health', timeout=3).read()"

CMD ["uvicorn", "inference:app", "--host", "0.0.0.0", "--port", "17025", "--workers", "1"]
