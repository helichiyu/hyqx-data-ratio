"""模型网关冒烟测试：硅基流动平替 + 磐智（idg）生产网关双后端。

后端配置与认证逻辑统一来自 ``operator/model_gateway.py``，本脚本只做通路
验证：embedding / rerank / chat / ASR / VLM。后端默认取 ``MODEL_BACKEND``
环境变量（缺省 idg），也可用 ``--backend`` 显式指定。

密钥不内置：硅基流动用 ``SILICONFLOW_API_KEY``，磐智用
``MODEL_GATEWAY_BASE_URL`` + ``MODEL_APP_KEY``，均从环境变量读取。

用法：

    python scripts/model_gateway_smoke.py                     # 跟随 MODEL_BACKEND（默认 idg）
    MODEL_BACKEND=siliconflow SILICONFLOW_API_KEY=sk-... \\
        python scripts/model_gateway_smoke.py                 # 硅基流动全量
    python scripts/model_gateway_smoke.py --capability embed,rerank
    python scripts/model_gateway_smoke.py --audio path/to.wav --image path/to.png
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DIR = REPO_ROOT / "operator"
if str(OPERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATOR_DIR))

from model_gateway import (  # noqa: E402
    ENDPOINTS,
    GatewayError,
    MODELS,
    auth_headers,
    gateway_request,
    resolve_backend,
    siliconflow_base_url,
)

SF = MODELS["siliconflow"]
IDG = MODELS["idg"]

#: 1x1 红色 PNG：没有 Pillow 或未提供图片时用于 VLM 通路验证。
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _sf_multipart(path: str, fields: dict[str, str], filename: str,
                  content: bytes, content_type: str) -> Any:
    base = siliconflow_base_url()
    headers = auth_headers("siliconflow")
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8")
    body += (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    body += content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(
        base + path,
        data=bytes(body),
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def _run(name: str, model: str, call: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        detail = call()
        return {
            "capability": name,
            "model": model,
            "ok": True,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "detail": detail,
        }
    except GatewayError as exc:
        return {
            "capability": name,
            "model": model,
            "ok": False,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "detail": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - 冒烟脚本逐项报告，不中断其它通路
        return {
            "capability": name,
            "model": model,
            "ok": False,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "detail": f"{type(exc).__name__}: {exc}",
        }


def _image_uri(path: str | None) -> str:
    if path:
        return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")
    try:
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), (220, 20, 20)).save(buffer, format="PNG")
        payload = buffer.getvalue()
    except Exception:  # noqa: BLE001 - 无 Pillow 时用内置 1x1 图
        payload = base64.b64decode(TINY_PNG_B64)
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def _check_siliconflow(wanted: set[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    chat_path = ENDPOINTS["siliconflow"]["chat"]
    embed_path = ENDPOINTS["siliconflow"]["embed"]
    rerank_path = ENDPOINTS["siliconflow"]["rerank"]
    asr_path = ENDPOINTS["siliconflow"]["asr"]

    if "embed" in wanted:
        for role in ("text_embed", "text_embed_long"):
            spec = SF[role]
            results.append(_run("embed", spec["model"], lambda s=spec: {
                "dimension": len(gateway_request(
                    "siliconflow", embed_path, {"model": s["model"], "input": "数据配比中心"},
                )["data"][0]["embedding"])
            }))

    if "rerank" in wanted:
        for role in ("text_rerank", "text_rerank_alt"):
            spec = SF[role]
            results.append(_run("rerank", spec["model"], lambda s=spec: gateway_request(
                "siliconflow", rerank_path,
                {"model": s["model"], "query": "数据质量",
                 "documents": ["数据质量评估", "今天天气很好"], "top_n": 2},
            )["results"]))

    if "chat" in wanted:
        for role in ("llm_small", "llm_mid", "llm_large"):
            spec = SF[role]
            results.append(_run("chat", spec["model"], lambda s=spec: gateway_request(
                "siliconflow", chat_path,
                {"model": s["model"], "max_tokens": 16,
                 "messages": [{"role": "user", "content": "只回复 OK"}]},
            )["choices"][0]["message"]["content"].strip()))

    if "asr" in wanted:
        spec = SF["asr"]
        audio_path = args.audio
        if not audio_path:
            default_audio = Path("D:/models/shared/paraformer-zh/example/asr_example.wav")
            audio_path = str(default_audio) if default_audio.is_file() else None
        if not audio_path or not Path(audio_path).is_file():
            results.append({"capability": "asr", "model": spec["model"], "ok": False,
                            "latencyMs": 0, "detail": "缺少音频文件，请用 --audio 指定"})
        else:
            audio = Path(audio_path).read_bytes()
            results.append(_run("asr", spec["model"], lambda: {
                "text": _sf_multipart(asr_path, {"model": SF["asr"]["model"]},
                                      Path(audio_path).name, audio, "audio/wav",
                                      ).get("text", "")[:80]
            }))

    if "vlm" in wanted:
        spec = SF["vlm_label"]
        uri = _image_uri(args.image)
        results.append(_run("vlm", spec["model"], lambda: gateway_request(
            "siliconflow", chat_path,
            {"model": spec["model"], "max_tokens": 32,
             "messages": [{"role": "user", "content": [
                 {"type": "text", "text": "图中主色是什么？只回答颜色"},
                 {"type": "image_url", "image_url": {"url": uri}},
             ]}]},
        )["choices"][0]["message"]["content"].strip()))

    return results


def _check_panzhi(wanted: set[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    if "chat" in wanted:
        for role in ("llm_small", "llm_mid"):
            spec = IDG[role]
            payload = {"model": spec["model"],
                       "messages": [{"role": "user", "content": "只回复 OK"}], "stream": False}
            results.append(_run("chat", spec["path"], lambda s=spec, p=payload: gateway_request(
                "idg", s["path"], p)["choices"][0]["message"]["content"].strip()))

    if "embed" in wanted:
        spec = IDG["text_embed"]
        payload = {"model": spec["model"], "input": "数据配比中心"}
        results.append(_run("embed", spec["path"], lambda: {
            "dimension": len(gateway_request("idg", spec["path"], payload)["data"][0]["embedding"])
        }))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="模型网关冒烟测试（硅基流动平替 / 磐智生产网关）")
    parser.add_argument("--backend", choices=("siliconflow", "idg", "panzhi", "sf", "test", "prod"),
                        default=None,
                        help="缺省跟随 MODEL_BACKEND 环境变量（默认 idg）")
    parser.add_argument("--capability", default="embed,rerank,chat,asr,vlm",
                        help="逗号分隔：embed,rerank,chat,asr,vlm,all")
    parser.add_argument("--audio", help="ASR 音频路径；默认用 paraformer 示例音频")
    parser.add_argument("--image", help="VLM 图片路径；默认用生成的纯色小图")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    args = parser.parse_args()

    backend = resolve_backend() if args.backend is None else resolve_backend(
        {"MODEL_BACKEND": args.backend})
    wanted = {item.strip() for item in args.capability.split(",") if item.strip()}
    if "all" in wanted:
        wanted = {"embed", "rerank", "chat", "asr", "vlm"}

    # 缺凭据时给出明确错误而不是逐项失败
    from model_gateway import backend_status
    status = backend_status()
    if not status["credentialsOk"]:
        missing = "、".join(status["missing"])
        print(f"后端 {backend} 缺少环境变量：{missing}（密钥不内置，启动时注入）")
        return 2

    if backend == "siliconflow":
        results = _check_siliconflow(wanted, args)
        base = siliconflow_base_url()
    else:
        results = _check_panzhi(wanted)
        base = os.getenv("MODEL_GATEWAY_BASE_URL", "(未设置)")

    payload = {"backend": backend, "baseUrl": base, "results": results}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in results:
            status_mark = "OK  " if item["ok"] else "FAIL"
            print(f"{status_mark} {item['capability']:<6} {item['model']:<36} {item['latencyMs']:>6}ms  {item['detail']}")
        print(f"\n成功 {sum(1 for item in results if item['ok'])}/{len(results)}")
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
