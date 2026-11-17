"""双后端模型网关：磐智（idg，默认）与硅基流动（siliconflow）。

生产走内网磐智签名网关（PATH 路由 + 签名头），联调阶段用硅基流动 OpenAI
兼容接口平替；两者请求/响应体均为 OpenAI 风格（chat 返回
``choices[0].message.content``，embedding 返回 ``data[].embedding``），仅认证
头与路由不同。差异收敛在本模块，调用方只面对 ``gateway_request`` 与 ``MODELS``。

后端在**启动时**用环境变量切换，不改代码、不重建镜像（docker compose 会把
下列变量透传进容器）：

    docker compose up -d --build                                        # 默认磐智（idg）
    MODEL_BACKEND=siliconflow SILICONFLOW_API_KEY=sk-xxx docker compose up -d
    MODEL_BACKEND=idg docker compose up -d

环境变量：

===========================  ==================================================
``MODEL_BACKEND``            ``idg``（默认；别名 ``panzhi``/``prod``）或
                             ``siliconflow``（别名 ``sf``/``test``）；非法值按 idg
``MODEL_GATEWAY_BASE_URL``   idg 网关基址，形如 ``http://<网关IP>:<端口>``
``MODEL_APP_ID``             idg APPID，默认 ``audioasr``
``MODEL_APP_KEY``            idg APPKEY，只从环境变量/Secret 注入
``MODEL_CAPABILITY``         覆盖 idg 签名 capability（仅平台为某路由单独
                             登记了 ASCII 能力名时使用）
``SILICONFLOW_BASE_URL``     默认 ``https://api.siliconflow.cn/v1``
``SILICONFLOW_API_KEY``      硅基流动密钥（兼容旧名 ``MODEL_GATEWAY_API_KEY``）
===========================  ==================================================

注意：密钥不写死在代码、配置或镜像里；idg 的签名时间戳与随机数每次调用
重新生成。选型依据见 ``docs/算子开发/模型选型与使用决策.md``。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Mapping

DEFAULT_IDG_APP_ID = "audioasr"
DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

BACKEND_ALIASES = {
    "idg": "idg",
    "panzhi": "idg",
    "prod": "idg",
    "siliconflow": "siliconflow",
    "sf": "siliconflow",
    "test": "siliconflow",
}

#: 各后端端点路径。idg 按 PATH 路由模型，端点即 ``MODELS["idg"][role]["path"]``
#: （embedding 路由已自带 ``/embeddings`` 后缀）；硅基流动是固定 REST 端点。
ENDPOINTS = {
    "idg": {"chat": "<model-path>", "embed": "<model-path>", "rerank": "<model-path>"},
    "siliconflow": {
        "chat": "/chat/completions",
        "embed": "/embeddings",
        "rerank": "/rerank",
        "asr": "/audio/transcriptions",
    },
}

#: 逻辑角色 → 两后端的模型配置。idg 的 ``path`` 必须严格按网关登记值，
#: 不改大小写、不自行拼写；``dims`` 供维度校验。
MODELS = {
    "idg": {
        "llm_small": {"path": "/Qwen2.5-3B-Instruct", "model": "Qwen2.5-3B-Instruct"},
        "llm_mid": {"path": "/Qwen3.5-9B", "model": "Qwen3.5-9B"},
        "llm_large": {"path": "/GLM-4-32B", "model": "GLM-4-32B"},
        "llm_xlarge": {"path": "/qwen3.6-35B-A3B-api", "model": "qwen3.6-35B-A3B-api"},
        "llm_produce": {"path": "/data-produce-1", "model": "qwen3.8-27b"},
        "llm_small_api": {"path": "/data-qwen35-2b-api", "model": "data-qwen35-2b-api"},
        "llm_mid_api": {"path": "/data-qwen3.5-4b", "model": "data-qwen3.5-4b"},
        "text_embed": {"path": "/Qwen3-Embedding-0.6B/embeddings", "model": "Qwen3-Embedding-0.6B", "dims": 1024},
        "text_embed_long": {"path": "/BAAI/bge-m3", "model": "BAAI/bge-m3", "dims": 1024},
        "image_embed": {"path": "/qwen3-vl-embedding-2b/embeddings", "model": "qwen3-vl-embedding-2b"},
        "image_embed_clip": {"path": "/chinese-clip-vit-huge-patch14", "model": "chinese-clip-vit-huge-patch14"},
        "vlm_label": {"path": "/qwen3-vl-8b-instruct", "model": "qwen3-vl-8b-instruct"},
        "vlm_7b": {"path": "/Qwen2.5-VL-7B-instruct", "model": "Qwen2.5-VL-7B-instruct"},
        "asr": {"path": "/Qwen3-ASR-0.6B", "model": "Qwen3-ASR-0.6B"},
        "ner": {"path": "/GLINER2.5-multi-v1", "model": "GLINER2.5-multi-v1"},
        "guard": {"path": "/qwen3guard-gen-0.6b", "model": "qwen3guard-gen-0.6b"},
    },
    "siliconflow": {
        "llm_small": {"model": "Qwen/Qwen2.5-7B-Instruct", "note": "无 3B，用 7B 近似"},
        "llm_mid": {"model": "Qwen/Qwen3.5-9B"},
        "llm_large": {"model": "THUDM/GLM-4-32B-0414"},
        "llm_xlarge": {"model": "Qwen/Qwen3.6-35B-A3B"},
        "llm_produce": {"model": "Qwen/Qwen3.8-27B"},
        "llm_mid_api": {"model": "Qwen/Qwen3.5-4B"},
        "text_embed": {"model": "Qwen/Qwen3-Embedding-0.6B", "dims": 1024},
        "text_embed_long": {"model": "BAAI/bge-m3", "dims": 1024},
        "text_rerank": {"model": "Qwen/Qwen3-Reranker-0.6B"},
        "text_rerank_alt": {"model": "BAAI/bge-reranker-v2-m3"},
        "image_embed": {"model": "Qwen/Qwen3-VL-Embedding-8B"},
        "vlm_label": {"model": "Qwen/Qwen3-VL-8B-Instruct"},
        "asr": {"model": "FunAudioLLM/SenseVoiceSmall"},
        "asr_alt": {"model": "Qwen/Qwen3-ASR-1.7B"},
    },
}


class GatewayError(RuntimeError):
    """网关调用失败（配置缺失、HTTP 错误、响应头校验失败等）。"""


def resolve_backend(env: Mapping[str, str] | None = None) -> str:
    """解析后端：``MODEL_BACKEND``（别名归一），非法或未设置按 ``idg``。"""

    source = os.environ if env is None else env
    raw = str(source.get("MODEL_BACKEND") or "idg").strip().lower()
    return BACKEND_ALIASES.get(raw, "idg")


def siliconflow_base_url(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    return str(source.get("SILICONFLOW_BASE_URL") or DEFAULT_SILICONFLOW_BASE_URL).rstrip("/")


def siliconflow_key(env: Mapping[str, str] | None = None) -> str:
    """硅基流动密钥：``SILICONFLOW_API_KEY`` 优先，兼容旧名 ``MODEL_GATEWAY_API_KEY``。"""

    source = os.environ if env is None else env
    key = str(source.get("SILICONFLOW_API_KEY") or source.get("MODEL_GATEWAY_API_KEY") or "").strip()
    if not key:
        raise GatewayError("缺少 SILICONFLOW_API_KEY 环境变量（硅基流动后端必需）")
    return key


def panzhi_headers(path: str, env: Mapping[str, str] | None = None) -> dict[str, str]:
    """磐智签名头：csid = APPID + capability(补 0 到 24 位) + uuid。

    capability 默认取 PATH 首段（≤24 字符）；平台单独登记了 ASCII 能力名时，
    用 ``MODEL_CAPABILITY`` 覆盖。时间戳与随机数每次调用重新生成。
    """

    source = os.environ if env is None else env
    app_id = str(source.get("MODEL_APP_ID") or DEFAULT_IDG_APP_ID).strip()
    app_key = str(source.get("MODEL_APP_KEY") or "").strip()
    if not app_key:
        raise GatewayError("缺少 MODEL_APP_KEY 环境变量（磐智后端必需）")
    capability = str(source.get("MODEL_CAPABILITY") or "").strip() or path.strip("/").split("/", 1)[0]
    if not capability or len(capability) > 24:
        raise GatewayError(f"capability 长度应为 1 至 24 个字符，实际：{capability!r}")
    timestamp = str(int(time.time()))
    csid = f"{app_id}{capability.ljust(24, '0')}{uuid.uuid4().hex}"
    server_param = base64.b64encode(
        json.dumps({"appid": app_id, "csid": csid}, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    checksum = hashlib.md5((app_key + timestamp + server_param).encode("utf-8")).hexdigest()
    return {
        "Content-Type": "application/json",
        "appKey": app_key,
        "X-Server-Param": server_param,
        "X-CurTime": timestamp,
        "X-CheckSum": checksum,
    }


def auth_headers(backend: str, path: str = "", env: Mapping[str, str] | None = None) -> dict[str, str]:
    """按后端生成认证头（含 Content-Type；multipart 场景由调用方覆盖 Content-Type）。"""

    if backend == "siliconflow":
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {siliconflow_key(env)}",
        }
    return panzhi_headers(path, env)


def _idg_base_url(env: Mapping[str, str]) -> str:
    base = str(env.get("MODEL_GATEWAY_BASE_URL") or "").strip()
    if not base:
        raise GatewayError("缺少 MODEL_GATEWAY_BASE_URL 环境变量（磐智后端必需，形如 http://<ip>:<port>）")
    return base.rstrip("/")


def gateway_request(
    backend: str,
    path: str,
    payload: Mapping[str, Any],
    *,
    timeout: int = 300,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """POST JSON 到指定后端并返回解析后的 JSON。

    idg 额外校验响应头：``X-Code`` 必须为空或 ``1000000``，``X-IsSync``
    不能为 ``false``（见 docs/参考记录/deployment-kit/03_IDG_MODEL_GATEWAY.md）。
    """

    source = os.environ if env is None else env
    backend = BACKEND_ALIASES.get(backend, backend)
    if backend == "siliconflow":
        url = siliconflow_base_url(source) + path
    else:
        url = _idg_base_url(source) + path
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=auth_headers(backend, path, source),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if backend == "idg":
                code = response.headers.get("X-Code")
                if code not in (None, "1000000"):
                    raise GatewayError(f"磐智网关 X-Code={code}，HTTP {response.status}")
                if response.headers.get("X-IsSync", "").strip().lower() == "false":
                    raise GatewayError("磐智网关返回异步确认，期望同步响应")
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise GatewayError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GatewayError(f"网关连接失败（{url}）：{exc.reason}") from exc


def backend_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """探针用：当前后端与凭据就绪情况（只报配置名，不回显密钥值）。"""

    source = os.environ if env is None else env
    backend = resolve_backend(source)
    missing: list[str] = []
    if backend == "siliconflow":
        if not (source.get("SILICONFLOW_API_KEY") or source.get("MODEL_GATEWAY_API_KEY")):
            missing.append("SILICONFLOW_API_KEY")
    else:
        if not str(source.get("MODEL_GATEWAY_BASE_URL") or "").strip():
            missing.append("MODEL_GATEWAY_BASE_URL")
        if not str(source.get("MODEL_APP_KEY") or "").strip():
            missing.append("MODEL_APP_KEY")
    return {
        "backend": backend,
        "credentialsOk": not missing,
        "missing": missing,
    }
