"""数据配比中心算子服务统一入口（S0 工程底座）。

单镜像、单入口：本文件只实现一次五端点、路径闸门、统一信封与按 ``operatorId``
调度，各算子不各自实现 HTTP 层。算子核心统一为
``core.run(input_path, params, seed, output_dir) -> dict``，不得依赖 FastAPI/HTTP。

端点（``{operatorId}`` 即 ``operator/`` 下的目录名）：

============================  ======  ==========================================
``/{operatorId}/healthz``     GET     探针（ready/device/weightsOk/dependencyStatus）
``/{operatorId}/uploadFile``  POST    multipart 上传，落盘 ``INPUT_DIR/<uniqueId>/``
``/{operatorId}/predict``     POST    JSON 或 multipart，执行 ``core.run``
``/{operatorId}/downloadFile`` GET    文件返回字节流，目录打 zip（二进制不套信封）
``/{operatorId}/removeFile``  POST   JSON ``{path}`` 或 ``{uniqueId}``，幂等清理
============================  ======  ==========================================

统一信封 ``{"code": 0|1, "msg": "...", "data": {...}}``；业务失败 ``code=1``。
协议细节见 ``docs/算子开发/算子工程契约.md``。
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import os
import re
import shutil
import sys
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any, Mapping

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException

ROOT = Path(__file__).resolve().parent
OPERATOR_ROOT = ROOT
MAP_PATH = ROOT / "map.json"
SHARED_WEIGHT_DIR = ROOT / "weights"

if str(OPERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(OPERATOR_ROOT))

logger = logging.getLogger("op-data-mixing")

DEFAULT_SEED = int(os.getenv("DEFAULT_SEED", "42"))
#: 平台单请求上限 10 MiB（任务书 3.2）；大文件由平台分片多次调用。
DEFAULT_MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
#: zip 解压后总量上限，防压缩炸弹。
DEFAULT_MAX_EXTRACT_BYTES = int(os.getenv("MAX_EXTRACT_BYTES", str(100 * 1024 * 1024)))
MAX_ZIP_MEMBERS = int(os.getenv("MAX_ZIP_MEMBERS", "10000"))
REQUIRE_X_TOKEN = os.getenv("REQUIRE_X_TOKEN", "false").lower() == "true"

UNIQUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
OPERATOR_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]{0,63}$")
UPLOAD_CHUNK_BYTES = 1024 * 1024

#: 四模态 + PDF/Parquet 收件白名单；zip 内的成员同样只接受这些后缀。
ALLOWED_SUFFIXES = frozenset(
    {
        # 文本
        ".txt", ".jsonl", ".json", ".xml", ".md", ".csv", ".tsv",
        # 文档
        ".pdf",
        # 图像
        ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".gif",
        # 音频
        ".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff",
        # 视频
        ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv",
        # 结构化产物
        ".parquet",
    }
)
ARCHIVE_SUFFIX = ".zip"

#: reasonCode -> (中文默认消息, HTTP 状态码)
REASON_CODES: dict[str, tuple[str, int]] = {
    "INVALID_REQUEST": ("请求参数不合法", 400),
    "INVALID_JSON": ("请求体不是合法 JSON 对象", 400),
    "INPUT_REQUIRED": ("请提供 inputFile（容器内绝对路径）、uniqueId 或 multipart file", 400),
    "INPUT_NOT_FOUND": ("输入路径不存在", 404),
    "PATH_INVALID": ("路径格式不合规：只接受 INPUT_DIR/OUTPUT_DIR 下的绝对路径", 400),
    "PATH_OUT_OF_BOUNDS": ("路径越界：只允许访问 INPUT_DIR 或 OUTPUT_DIR 之下", 400),
    "PATH_SYMLINK": ("路径包含符号链接，拒绝访问", 400),
    "ROOT_PATH_FORBIDDEN": ("禁止操作输入/输出根目录本身", 400),
    "UNIQUE_ID_INVALID": ("uniqueId 只能包含字母、数字、点、下划线和连字符，且首字符为字母或数字", 400),
    "UNSUPPORTED_FILE_TYPE": ("文件后缀不在收件白名单内", 400),
    "UPLOAD_TOO_LARGE": ("单次上传超过大小上限", 413),
    "ZIP_INVALID": ("上传内容不是有效的 zip 压缩包", 400),
    "ZIP_EMPTY": ("zip 内没有白名单允许的文件", 400),
    "ZIP_TOO_LARGE": ("zip 解压后总量超过上限", 413),
    "AUTH_REQUIRED": ("缺少 X-Token 请求头", 401),
    "NOT_FOUND": ("接口或资源不存在", 404),
    "METHOD_NOT_ALLOWED": ("HTTP 方法不允许", 405),
    "CORE_IMPORT_FAILED": ("算子核心不可导入", 503),
    "DEPENDENCY_UNAVAILABLE": ("算子依赖不可用（模型/权重/外部服务）", 503),
    "OPERATOR_NOT_IMPLEMENTED": ("算子尚未实现（S0 骨架）", 200),
    "CONTRACT_VIOLATION": ("算子返回值不符合 core.run 契约", 500),
    "INTERNAL_ERROR": ("服务内部错误", 500),
}


class OperatorRuntime:
    """单个算子的运行期元信息与惰性导入的核心模块。"""

    def __init__(self, meta: Mapping[str, Any]) -> None:
        self.meta = dict(meta)
        self.operator_id: str = str(self.meta["operatorId"])
        self.semantic_code: str = str(self.meta.get("semanticCode") or self.operator_id)
        self.version: str = str(self.meta.get("version") or "0.1.0")
        self.requires_weights: bool = bool(self.meta.get("requiresWeights", False))
        self._core = self.meta.get("core")
        self._import_error: str | None = None
        self._loaded = self._core is not None

    @property
    def package_dir(self) -> Path:
        return OPERATOR_ROOT / self.operator_id / self.operator_id

    def load_core(self) -> Any:
        if self._loaded:
            return self._core
        try:
            self._core = _import_operator_core(self.operator_id)
        except Exception as exc:  # noqa: BLE001 - 导入失败要转成明确 reasonCode
            self._import_error = f"{type(exc).__name__}: {exc}"
            logger.error("算子核心导入失败 %s: %s", self.operator_id, self._import_error)
            raise
        self._loaded = True
        return self._core

    @property
    def import_error(self) -> str | None:
        return self._import_error

    def weights_ok(self) -> bool:
        if not self.requires_weights:
            return True
        root = _resolve_weights_root()
        if _has_weight_files(root / "shared"):
            return True
        return _has_weight_files(root / self.operator_id)


def _import_operator_core(operator_id: str) -> Any:
    """按目录名加载同名包并返回 ``core`` 子模块。

    包名含连字符时不能写 ``import dm-x``，但 importlib 可以按路径注册包名；
    包内 ``from .utils import ...`` 仍按相对导入解析。
    """

    if operator_id in sys.modules:
        return importlib.import_module(f"{operator_id}.core")

    package_dir = OPERATOR_ROOT / operator_id
    init_file = package_dir / "__init__.py"
    if not init_file.is_file():
        raise ModuleNotFoundError(f"算子包不存在：{init_file}")

    spec = importlib.util.spec_from_file_location(
        operator_id,
        init_file,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为 {operator_id} 创建导入 spec")
    package = importlib.util.module_from_spec(spec)
    sys.modules[operator_id] = package
    spec.loader.exec_module(package)
    return importlib.import_module(f"{operator_id}.core")


def _resolve_weights_root() -> Path:
    """权重根：``WEIGHTS_DIR`` > 本机模型仓（``D:/models``、``/models``）> 镜像内 weights。"""

    configured = os.getenv("WEIGHTS_DIR")
    if configured:
        return Path(configured).resolve()
    for candidate in (Path("D:/models"), Path("/models")):
        if (candidate / "shared").is_dir():
            return candidate.resolve()
    return SHARED_WEIGHT_DIR


def _has_weight_files(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    ignorable = {".gitkeep", "SHA256SUMS", "README.md"}
    return any(path.is_file() and path.name not in ignorable for path in directory.rglob("*"))


def _load_registry() -> dict[str, dict[str, Any]]:
    payload = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    operators = payload.get("operators") or []
    if not operators:
        raise RuntimeError("map.json 没有登记任何算子")
    return {str(item["operatorId"]): dict(item) for item in operators}


def _device_info() -> dict[str, Any]:
    """运行期设备：请求值、实际值、CUDA 可用性与回落原因。

    以 ``torch`` 的真实状态为准，不做"假装 GPU"；torch 缺失或 CUDA 不可用时
    返回 ``device=cpu`` 并给出 ``fallbackReason``。
    """

    requested = (os.getenv("DEVICE") or "auto").strip().lower()
    if requested not in {"cpu", "auto"} and not requested.startswith("cuda"):
        requested = "auto"
    info: dict[str, Any] = {
        "requested": requested,
        "device": "cpu",
        "cudaAvailable": False,
    }
    try:
        import torch
    except Exception as exc:  # noqa: BLE001 - 探针只报告状态，不中断
        info["fallbackReason"] = f"torch 不可用：{type(exc).__name__}"
        return info

    info["torchVersion"] = torch.__version__
    info["cudaRuntime"] = torch.version.cuda
    try:
        available = bool(torch.cuda.is_available())
    except Exception as exc:  # noqa: BLE001
        info["fallbackReason"] = f"CUDA 初始化失败：{type(exc).__name__}"
        return info
    info["cudaAvailable"] = available
    if requested == "cpu":
        return info
    if not available:
        if requested != "auto":
            info["fallbackReason"] = "CUDA 不可用，回落 CPU"
        return info

    device = requested if ":" in requested else "cuda:0"
    try:
        index = int(device.split(":", 1)[1]) if ":" in device else 0
        info["gpuName"] = torch.cuda.get_device_name(index)
    except Exception:  # noqa: BLE001 - 设备名仅用于展示
        pass
    info["device"] = device
    return info


def _envelope(code: int, msg: str, data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "msg": msg, "data": dict(data or {})}


def _error(reason_code: str, msg: str | None = None, *, status: int | None = None,
           data: Mapping[str, Any] | None = None) -> JSONResponse:
    default_msg, default_status = REASON_CODES.get(reason_code, ("未知错误", 500))
    body = dict(data or {})
    body["reasonCode"] = reason_code
    return JSONResponse(
        status_code=status or default_status,
        content=_envelope(1, msg or default_msg, body),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(UPLOAD_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(path: Path) -> str:
    """输入指纹：文件按内容哈希；目录按相对路径+大小+内容哈希排序后聚合。"""

    digest = hashlib.sha256()
    if path.is_dir():
        digest.update(b"dir\0")
        for item in sorted(path.rglob("*"), key=lambda p: p.relative_to(path).as_posix()):
            relative = item.relative_to(path).as_posix()
            if item.is_symlink():
                raise ValueError(f"输入目录包含符号链接，拒绝处理：{relative}")
            if not item.is_file():
                continue
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(item.stat().st_size).encode("ascii"))
            digest.update(b"\0")
            digest.update(_sha256_file(item).encode("ascii"))
            digest.update(b"\0")
    elif path.is_file():
        digest.update(b"file\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
    else:
        raise FileNotFoundError(str(path))
    return digest.hexdigest()


def _params_hash(params: Mapping[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_path(raw: Any, roots: list[Path], *, reject_root: bool = False) -> Path:
    """路径闸门：绝对路径、落在允许根内、拒绝 file:// / ~ / 控制字符 / 符号链接。"""

    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(REASON_CODES["PATH_INVALID"][0])
    text = raw.strip()
    lowered = text.lower()
    if lowered.startswith("file://") or text.startswith("~"):
        raise ValueError("路径格式不合规：只接受绝对路径，不接受 file:// 或 ~")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError("路径格式不合规：含控制字符")

    candidate = Path(text)
    if not candidate.is_absolute():
        raise ValueError("路径必须是绝对路径")

    resolved = candidate.resolve(strict=False)
    for root in roots:
        resolved_root = root.resolve()
        try:
            relative = resolved.relative_to(resolved_root)
        except ValueError:
            continue
        if reject_root and not relative.parts:
            raise RootPathError("禁止操作输入/输出根目录本身")
        cursor = resolved_root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise SymlinkPathError(f"路径包含符号链接，拒绝访问：{raw}")
        return resolved
    raise OutOfBoundsError(
        "路径越界，只允许访问 "
        + " 与 ".join(root.as_posix() for root in roots)
        + " 之下"
    )


class RootPathError(ValueError):
    """目标为允许根目录本身。"""


class SymlinkPathError(ValueError):
    """路径包含符号链接。"""


class OutOfBoundsError(ValueError):
    """路径落在允许根之外。"""


def _path_error(exc: ValueError) -> JSONResponse:
    if isinstance(exc, RootPathError):
        return _error("ROOT_PATH_FORBIDDEN", str(exc))
    if isinstance(exc, SymlinkPathError):
        return _error("PATH_SYMLINK", str(exc))
    if isinstance(exc, OutOfBoundsError):
        return _error("PATH_OUT_OF_BOUNDS", str(exc))
    return _error("PATH_INVALID", str(exc))


def _safe_filename(raw: str | None, fallback: str = "upload.bin") -> str:
    name = Path(str(raw or "").replace("\\", "/")).name
    name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127).strip()
    return name or fallback


def _extract_zip(archive_path: Path, destination: Path, max_bytes: int) -> tuple[list[str], list[str]]:
    """解压抹平到 destination：只取 basename（防 zip-slip）、白名单过滤、限制总量。"""

    files: list[str] = []
    skipped: list[str] = []
    total = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ZIP_MEMBERS:
                raise ValueError(f"zip 成员数超过上限 {MAX_ZIP_MEMBERS}")
            for member in members:
                name = Path(member.filename.replace("\\", "/")).name
                if member.is_dir() or not name:
                    continue
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    skipped.append(f"{name}（符号链接）")
                    continue
                if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
                    skipped.append(name)
                    continue
                if name in files:
                    skipped.append(f"{name}（重名，保留第一个）")
                    continue
                total += member.file_size
                if total > max_bytes:
                    raise OverLargeZip(f"zip 解压后总量超过上限 {max_bytes // (1024 ** 2)} MiB")
                with (destination / name).open("wb") as sink:
                    with archive.open(member) as source:
                        shutil.copyfileobj(source, sink, UPLOAD_CHUNK_BYTES)
                files.append(name)
    except zipfile.BadZipFile as exc:
        raise InvalidZip("上传内容不是有效的 zip 压缩包") from exc
    return files, skipped


class InvalidZip(ValueError):
    """不是有效 zip。"""


class OverLargeZip(ValueError):
    """zip 解压总量超限。"""


def _prepare_run_input(input_path: Path, run_dir: Path, max_bytes: int) -> tuple[Path, list[str]]:
    """把 zip 输入解压到 run 目录后交给算子；其他输入原样传递。"""

    if input_path.is_file() and input_path.suffix.lower() == ARCHIVE_SUFFIX:
        extracted = run_dir / "_input" / "extracted"
        shutil.rmtree(extracted, ignore_errors=True)
        extracted.mkdir(parents=True, exist_ok=True)
        files, skipped = _extract_zip(input_path, extracted, max_bytes)
        if not files:
            raise InvalidZip("zip 内没有白名单允许的文件")
        return extracted, skipped
    return input_path, []


def _read_params(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"params 不是合法 JSON：{exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ValueError("params 必须是 JSON 对象")
    return raw


def _read_seed(raw: Any) -> int:
    if raw is None or raw == "":
        return DEFAULT_SEED
    try:
        seed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("seed 必须是整数") from exc
    return seed


def create_app(
    input_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    registry: Mapping[str, Mapping[str, Any]] | None = None,
    max_upload_bytes: int | None = None,
    max_extract_bytes: int | None = None,
) -> FastAPI:
    """创建单入口应用；测试可注入临时目录、注册表与上传上限。"""

    input_root = Path(input_dir or os.getenv("INPUT_DIR") or ROOT / "runtime" / "input").resolve()
    output_root = Path(output_dir or os.getenv("OUTPUT_DIR") or ROOT / "runtime" / "output").resolve()
    input_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    tmp_root = output_root / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)

    upload_limit = int(max_upload_bytes if max_upload_bytes is not None else DEFAULT_MAX_UPLOAD_BYTES)
    extract_limit = int(max_extract_bytes if max_extract_bytes is not None else DEFAULT_MAX_EXTRACT_BYTES)
    runtimes = {key: OperatorRuntime(meta) for key, meta in (registry or _load_registry()).items()}
    # 启动期探测一次设备：healthz 只读结果，避免首次探针在请求内初始化 CUDA 导致超时。
    device_info = _device_info()
    run_locks: dict[str, threading.Lock] = {}
    locks_guard = threading.Lock()

    app = FastAPI(title="op-data-mixing", version=str(_app_version()))
    app.state.input_root = input_root
    app.state.output_root = output_root
    app.state.runtimes = runtimes

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item.get('loc', []))}: {item.get('msg', '')}"
            for item in exc.errors()
        )
        return _error("INVALID_REQUEST", f"请求参数校验失败：{details}")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _error("NOT_FOUND")
        if exc.status_code == 405:
            return _error("METHOD_NOT_ALLOWED")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(1, str(exc.detail), {"reasonCode": "HTTP_ERROR"}),
        )

    def _acquire_lock(run_id: str) -> threading.Lock:
        with locks_guard:
            return run_locks.setdefault(run_id, threading.Lock())

    def _check_token(request: Request) -> JSONResponse | None:
        if REQUIRE_X_TOKEN and not request.headers.get("X-Token", "").strip():
            return _error("AUTH_REQUIRED")
        return None

    def _healthz(runtime: OperatorRuntime) -> dict[str, Any]:
        core_status = "ok"
        try:
            runtime.load_core()
        except Exception:  # noqa: BLE001 - 探针只报告状态，不抛出
            core_status = "import_failed"
        ready = core_status == "ok" and input_root.is_dir() and output_root.is_dir()
        weights_ok = runtime.weights_ok()
        ffmpeg_ok = shutil.which("ffmpeg") is not None
        device = device_info
        data = {
            "ready": ready,
            "operatorId": runtime.operator_id,
            "semanticCode": runtime.semantic_code,
            "version": runtime.version,
            "device": device["device"],
            "deviceRequested": device["requested"],
            "cudaAvailable": device["cudaAvailable"],
            "weightsOk": weights_ok,
            "dependencyStatus": {
                "core": core_status,
                "ffmpeg": "ok" if ffmpeg_ok else "missing",
                "weights": "not_required" if not runtime.requires_weights else ("present" if weights_ok else "missing"),
            },
            "inputDir": input_root.as_posix(),
            "outputDir": output_root.as_posix(),
        }
        for key in ("gpuName", "cudaRuntime", "torchVersion"):
            if key in device:
                data[key] = device[key]
        if "fallbackReason" in device:
            data["deviceFallbackReason"] = device["fallbackReason"]
        if runtime.import_error:
            data["importError"] = runtime.import_error
        return _envelope(0 if ready else 1, "success" if ready else "算子未就绪", data)

    def _aggregate_health() -> dict[str, Any]:
        probes = [_healthz(runtime) for runtime in runtimes.values()]
        ready = sum(1 for probe in probes if probe["code"] == 0 and probe["data"]["ready"])
        status = "ok" if ready == len(probes) else "degraded"
        try:
            from model_gateway import backend_status

            gateway = backend_status()
        except Exception:  # noqa: BLE001 - 探针只报告状态，不中断
            gateway = {
                "backend": os.getenv("MODEL_BACKEND", "idg"),
                "credentialsOk": False,
                "missing": ["model_gateway"],
            }
        return _envelope(
            0 if status == "ok" else 1,
            "success" if status == "ok" else "部分算子未就绪",
            {
                "service": "op-data-mixing",
                "version": str(_app_version()),
                "status": status,
                "operatorCount": len(probes),
                "readyCount": ready,
                "modelBackend": gateway,
            },
        )

    async def _upload(runtime: OperatorRuntime, request: Request,
                      uniqueId: str | None = Query(default=None)) -> Any:
        auth_error = _check_token(request)
        if auth_error is not None:
            return auth_error

        try:
            form = await request.form()
        except Exception as exc:  # noqa: BLE001 - multipart 解析失败按参数错误
            return _error("INVALID_REQUEST", f"multipart 解析失败：{exc}")
        upload = form.get("file")
        if upload is None or not getattr(upload, "filename", None):
            return _error("INVALID_REQUEST", "multipart 中缺少 file 字段")
        unique_id = uniqueId or form.get("uniqueId")
        if unique_id is not None and not UNIQUE_ID_RE.fullmatch(str(unique_id)):
            return _error("UNIQUE_ID_INVALID")

        raw_name = _safe_filename(str(upload.filename))
        suffix = Path(raw_name).suffix.lower()
        if suffix != ARCHIVE_SUFFIX and suffix not in ALLOWED_SUFFIXES:
            return _error("UNSUPPORTED_FILE_TYPE", f"文件后缀 {suffix or '(无后缀)'} 不在收件白名单内")

        blob = tmp_root / f"upload_{uuid.uuid4().hex}"
        received = 0
        try:
            with blob.open("wb") as sink:
                while True:
                    chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > upload_limit:
                        return _error(
                            "UPLOAD_TOO_LARGE",
                            f"单次上传超过上限 {upload_limit // (1024 ** 2)} MiB",
                        )
                    sink.write(chunk)
            if received == 0:
                return _error("INVALID_REQUEST", "请求体里没有文件内容（file 字段为空）")
            if unique_id is None:
                unique_id = f"up_{_sha256_file(blob)[:16]}"

            destination = input_root / str(unique_id)
            if destination.is_symlink():
                return _error("PATH_SYMLINK", f"目标目录是符号链接，拒绝覆盖：{destination}")
            if destination.exists():
                shutil.rmtree(destination)
            destination.mkdir(parents=True)

            if suffix == ARCHIVE_SUFFIX:
                try:
                    files, skipped = _extract_zip(blob, destination, extract_limit)
                except InvalidZip as exc:
                    shutil.rmtree(destination, ignore_errors=True)
                    return _error("ZIP_INVALID", str(exc))
                except OverLargeZip as exc:
                    shutil.rmtree(destination, ignore_errors=True)
                    return _error("ZIP_TOO_LARGE", str(exc))
                if not files:
                    shutil.rmtree(destination, ignore_errors=True)
                    return _error("ZIP_EMPTY")
            else:
                shutil.move(str(blob), str(destination / raw_name))
                files, skipped = [raw_name], []

            return _envelope(
                0,
                "success" if not skipped else f"success（跳过 {len(skipped)} 个非白名单/重名文件）",
                {
                    "operatorId": runtime.operator_id,
                    "uniqueId": unique_id,
                    "directory": destination.as_posix(),
                    "files": files,
                    "filePaths": [(destination / name).as_posix() for name in files],
                    "skipped": skipped,
                },
            )
        finally:
            blob.unlink(missing_ok=True)

    async def _predict(runtime: OperatorRuntime, request: Request) -> Any:
        auth_error = _check_token(request)
        if auth_error is not None:
            return auth_error

        unique_id: str | None = None
        input_file: str | None = None
        params_raw: Any = None
        seed_raw: Any = None
        upload = None
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            try:
                form = await request.form()
            except Exception as exc:  # noqa: BLE001
                return _error("INVALID_REQUEST", f"multipart 解析失败：{exc}")
            unique_id = form.get("uniqueId") or None
            input_file = form.get("inputFile") or None
            params_raw = form.get("params")
            seed_raw = form.get("seed")
            upload = form.get("file")
            if upload is not None and not getattr(upload, "filename", None):
                upload = None
        else:
            try:
                body = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                return _error("INVALID_JSON")
            if not isinstance(body, dict):
                return _error("INVALID_JSON", "请求体必须是 JSON 对象")
            unique_id = body.get("uniqueId") or None
            input_file = body.get("inputFile") or None
            params_raw = body.get("params")
            seed_raw = body.get("seed")

        if unique_id is not None and not UNIQUE_ID_RE.fullmatch(str(unique_id)):
            return _error("UNIQUE_ID_INVALID")
        try:
            params = _read_params(params_raw)
            seed = _read_seed(seed_raw)
        except ValueError as exc:
            return _error("INVALID_REQUEST", str(exc))

        provided = sum(1 for item in (upload, input_file, unique_id) if item)
        if provided == 0:
            return _error("INPUT_REQUIRED")
        if provided > 1:
            return _error("INVALID_REQUEST", "inputFile、uniqueId、multipart file 三选一，不能同时传")

        if upload is not None:
            raw_name = _safe_filename(str(upload.filename))
            source_blob = tmp_root / f"predict_{uuid.uuid4().hex}_{raw_name}"
            received = 0
            exceeded = False
            with source_blob.open("wb") as sink:
                while True:
                    chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > upload_limit:
                        exceeded = True
                        break
                    sink.write(chunk)
            if exceeded:
                source_blob.unlink(missing_ok=True)
                return _error(
                    "UPLOAD_TOO_LARGE",
                    f"单次上传超过上限 {upload_limit // (1024 ** 2)} MiB",
                )
            if received == 0:
                source_blob.unlink(missing_ok=True)
                return _error("INVALID_REQUEST", "multipart file 内容为空")
            input_path = source_blob
            staged_upload = True
        elif input_file:
            try:
                input_path = _safe_path(input_file, [input_root, output_root])
            except ValueError as exc:
                return _path_error(exc)
            if not input_path.exists():
                return _error("INPUT_NOT_FOUND", f"inputFile 指向的路径不存在：{input_file}")
            staged_upload = False
        else:
            assert unique_id is not None
            candidate = input_root / str(unique_id)
            if not candidate.exists():
                return _error("INPUT_NOT_FOUND", f"uniqueId 对应目录不存在：{unique_id}")
            input_path = candidate
            staged_upload = False

        try:
            fingerprint = _fingerprint(input_path)
        except (OSError, ValueError) as exc:
            if staged_upload:
                input_path.unlink(missing_ok=True)
            return _error("PATH_INVALID", f"输入指纹计算失败：{exc}")

        try:
            runtime.load_core()
        except Exception:
            if staged_upload:
                input_path.unlink(missing_ok=True)
            return _error(
                "CORE_IMPORT_FAILED",
                f"算子核心不可导入：{runtime.import_error}",
                data={"operatorId": runtime.operator_id},
            )

        params_digest = _params_hash(params)
        run_id = hashlib.sha256(
            f"{fingerprint}|{runtime.version}|{params_digest}|{seed}".encode("utf-8")
        ).hexdigest()[:16]
        run_dir = output_root / runtime.operator_id / run_id
        base_data = {
            "operatorId": runtime.operator_id,
            "semanticCode": runtime.semantic_code,
            "operatorVersion": runtime.version,
            "paramsHash": f"sha256:{params_digest}",
            "seed": seed,
            "runId": run_id,
            "inputFingerprint": f"sha256:{fingerprint}",
            "outputDir": run_dir.as_posix(),
        }

        lock = _acquire_lock(run_id)
        with lock:
            cached = run_dir / "result.json"
            if cached.is_file():
                try:
                    cached_payload = json.loads(cached.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    cached_payload = None
                if isinstance(cached_payload, dict) and cached_payload.get("status") == "succeeded":
                    data = dict(cached_payload.get("data") or {})
                    data["cached"] = True
                    return _envelope(0, "success", data)

            run_dir.mkdir(parents=True, exist_ok=True)
            prepared_input = input_path
            try:
                if staged_upload:
                    staged_dir = run_dir / "_input"
                    staged_dir.mkdir(parents=True, exist_ok=True)
                    destination = staged_dir / _safe_filename(input_path.name)
                    destination.unlink(missing_ok=True)
                    shutil.move(str(input_path), str(destination))
                    prepared_input = destination
                else:
                    prepared_input, _ = _prepare_run_input(input_path, run_dir, extract_limit)
            except InvalidZip as exc:
                return _error("ZIP_INVALID", str(exc), data=base_data)
            except OverLargeZip as exc:
                return _error("ZIP_TOO_LARGE", str(exc), data=base_data)
            except OSError as exc:
                return _error("INTERNAL_ERROR", f"输入整理失败：{exc}", data=base_data)

            logger.info("predict start operator=%s runId=%s input=%s", runtime.operator_id, run_id, prepared_input)
            try:
                result = runtime.load_core().run(
                    input_path=str(prepared_input),
                    params=params,
                    seed=seed,
                    output_dir=str(run_dir),
                )
            except NotImplementedError as exc:
                reason = str(exc.args[0]) if exc.args else "OPERATOR_NOT_IMPLEMENTED"
                msg = REASON_CODES.get(reason, ("算子尚未实现", 200))[0]
                return _error(reason, msg, status=200, data=base_data)
            except (ImportError, ModuleNotFoundError) as exc:
                logger.error("算子依赖不可用 %s: %s", runtime.operator_id, exc)
                return _error("DEPENDENCY_UNAVAILABLE", data={**base_data, "detail": str(exc)})
            except Exception as exc:  # noqa: BLE001 - 未预期异常转标准错误并留日志
                if type(exc).__name__ == "DependencyUnavailable" or getattr(
                    exc, "reason_code", None
                ) == "DEPENDENCY_UNAVAILABLE":
                    logger.error("算子依赖不可用 %s: %s", runtime.operator_id, exc)
                    return _error(
                        "DEPENDENCY_UNAVAILABLE",
                        str(exc),
                        data={**base_data, "detail": str(exc)},
                    )
                logger.exception("算子执行失败 %s runId=%s", runtime.operator_id, run_id)
                (run_dir / "error.log").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
                return _error("INTERNAL_ERROR", data={**base_data, "detail": f"{type(exc).__name__}: {exc}"})

            if not isinstance(result, dict):
                return _error(
                    "CONTRACT_VIOLATION",
                    f"core.run 必须返回 dict，实际为 {type(result).__name__}",
                    data=base_data,
                )

            result_jsonl = run_dir / "result.jsonl"
            data: dict[str, Any] = {
                **base_data,
                "modelVersion": None,
                "treeVersion": None,
                "sampleCount": None,
                "successCount": None,
                "failedCount": 0,
                "failedSamples": [],
                "metrics": {},
                "artifacts": [],
                "outputFilePath": (result_jsonl if result_jsonl.exists() else cached).as_posix(),
            }
            data.update(result)
            data.update(base_data)  # 协议字段由 HTTP 层兜底，算子不得改写
            data["cached"] = False

            payload = {"status": "succeeded", "data": data}
            temp_result = run_dir / ".result.json.tmp"
            temp_result.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_result.replace(cached)
            logger.info("predict done operator=%s runId=%s", runtime.operator_id, run_id)
            return _envelope(0, "success", data)

    def _download(runtime: OperatorRuntime, request: Request, path: str = Query(...)) -> Any:
        auth_error = _check_token(request)
        if auth_error is not None:
            return auth_error
        try:
            target = _safe_path(path, [input_root, output_root])
        except ValueError as exc:
            return _path_error(exc)
        if not target.exists():
            return _error("INPUT_NOT_FOUND", f"路径不存在：{path}")
        if target.is_file():
            return FileResponse(target, filename=target.name)
        zip_path = tmp_root / f"download_{uuid.uuid4().hex}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in sorted(target.rglob("*")):
                    if item.is_file() and not item.is_symlink():
                        archive.write(item, item.relative_to(target).as_posix())
        except OSError as exc:
            zip_path.unlink(missing_ok=True)
            return _error("INTERNAL_ERROR", f"目录打包失败：{exc}")
        return FileResponse(
            zip_path,
            filename=f"{target.name}.zip",
            background=BackgroundTask(zip_path.unlink, missing_ok=True),
        )

    async def _remove(runtime: OperatorRuntime, request: Request) -> Any:
        auth_error = _check_token(request)
        if auth_error is not None:
            return auth_error
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _error("INVALID_JSON")
        if not isinstance(body, dict):
            return _error("INVALID_JSON", "请求体必须是 JSON 对象")
        raw_path = body.get("path")
        unique_id = body.get("uniqueId")
        if raw_path:
            try:
                target = _safe_path(raw_path, [input_root, output_root], reject_root=True)
            except ValueError as exc:
                return _path_error(exc)
        elif unique_id:
            if not UNIQUE_ID_RE.fullmatch(str(unique_id)):
                return _error("UNIQUE_ID_INVALID")
            target = input_root / str(unique_id)
        else:
            return _error("INVALID_REQUEST", "请提供 path 或 uniqueId")

        if target.is_symlink():
            return _error("PATH_SYMLINK", f"目标是符号链接，拒绝删除：{target}")
        removed = False
        if target.is_dir():
            shutil.rmtree(target)
            removed = True
        elif target.exists():
            target.unlink()
            removed = True
        return _envelope(0, "success", {"removed": removed, "path": target.as_posix()})

    def make_healthz_endpoint(runtime: OperatorRuntime):
        def endpoint() -> dict[str, Any]:
            return _healthz(runtime)

        return endpoint

    def make_upload_endpoint(runtime: OperatorRuntime):
        async def endpoint(request: Request, uniqueId: str | None = Query(default=None)) -> Any:
            return await _upload(runtime, request, uniqueId)

        return endpoint

    def make_predict_endpoint(runtime: OperatorRuntime):
        async def endpoint(request: Request) -> Any:
            return await _predict(runtime, request)

        return endpoint

    def make_download_endpoint(runtime: OperatorRuntime):
        def endpoint(request: Request, path: str = Query(...)) -> Any:
            return _download(runtime, request, path)

        return endpoint

    def make_remove_endpoint(runtime: OperatorRuntime):
        async def endpoint(request: Request) -> Any:
            return await _remove(runtime, request)

        return endpoint

    for operator_id, runtime in runtimes.items():
        if not OPERATOR_ID_RE.fullmatch(operator_id):
            raise RuntimeError(f"非法 operatorId：{operator_id}")
        app.add_api_route(
            f"/{operator_id}/healthz", make_healthz_endpoint(runtime),
            methods=["GET"], name=f"{operator_id}_healthz",
        )
        app.add_api_route(
            f"/{operator_id}/uploadFile", make_upload_endpoint(runtime),
            methods=["POST"], name=f"{operator_id}_upload",
        )
        app.add_api_route(
            f"/{operator_id}/predict", make_predict_endpoint(runtime),
            methods=["POST"], name=f"{operator_id}_predict",
        )
        app.add_api_route(
            f"/{operator_id}/downloadFile", make_download_endpoint(runtime),
            methods=["GET"], name=f"{operator_id}_download",
        )
        app.add_api_route(
            f"/{operator_id}/removeFile", make_remove_endpoint(runtime),
            methods=["POST"], name=f"{operator_id}_remove",
        )
    app.add_api_route("/health", lambda: _aggregate_health(), methods=["GET"], name="service_health")
    app.add_api_route("/healthz", lambda: _aggregate_health(), methods=["GET"], name="service_healthz")
    return app


def _app_version() -> str:
    try:
        return str(json.loads(MAP_PATH.read_text(encoding="utf-8")).get("version") or "0.1.0")
    except (OSError, json.JSONDecodeError):
        return "0.1.0"


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("inference:app", host="0.0.0.0", port=int(os.getenv("PORT", "17025")))
