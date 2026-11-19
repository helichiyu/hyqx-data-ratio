# 算子工程目录（单镜像 `op-data-mixing`）

**本目录是唯一的 Docker 构建上下文。** 14 个算子共用根 `inference.py`、`map.json`、`requirements.txt` 与同一个镜像/容器，不按算子拆镜像、不按算子另起端口。

```text
operator/
├── Dockerfile / .dockerignore / docker-compose.yml
├── inference.py               # 唯一 HTTP 入口：五端点 + /health + 按 operatorId 调度
├── requirements.txt / map.json
├── baseline/                  # 树快照、六类来源映射、阈值（进镜像）
├── weights/                   # 单一权重根：shared/ 共享模型，<operatorId>/ 私有模型
├── _template/                 # 模板（不登记为算子，不进镜像）
└── dm-<对象>-<动作>/          # 目录名 = 包名 = operatorId（不嵌套）
    ├── __init__.py
    ├── core.py                # core.run(input_path, params, seed, output_dir) -> dict
    ├── configs/               # 阈值、标签映射、规则
    └── utils/                 # 解析、特征、评分、校验
```

## 启动与验证

```bash
# 本机启动（在 operator/ 下）
python -m uvicorn inference:app --host 0.0.0.0 --port 17025

# 从仓库根验证全部探针
python scripts/check_healthz.py --base-url http://127.0.0.1:17025

# 契约测试（仓库根）
python -m pytest tests operator/_template/tests

# 单镜像（构建前先暂存权重：python scripts/stage_weights.py）
docker compose up -d --build
```

> 网络受限环境：`registry-1.docker.io` 直连可能超时（`load metadata ... EOF`）。
> 先从镜像仓拉基础镜像再重打标签，无需改 Dockerfile：
> `docker pull docker.m.daocloud.io/library/python:3.12-slim-bookworm && docker tag docker.m.daocloud.io/library/python:3.12-slim-bookworm python:3.12-slim-bookworm`

协议、错误码、路径闸门、幂等与 Schema 见 [`docs/算子开发/算子工程契约.md`](../docs/算子开发/算子工程契约.md)；模型选型、测试平替与下载清单见 [`docs/算子开发/模型选型与使用决策.md`](../docs/算子开发/模型选型与使用决策.md)。

## 运行设备

- 设备优先级：环境变量 `DEVICE` > 算子 `configs/*.json` 的 `device` > `auto`。`auto` 在 CUDA 可用时使用 `cuda:0`，否则回落 CPU；显式 `cuda` 但 CUDA 不可用时同样回落，不阻塞启动。
- 镜像内 torch 的 CUDA runtime 不高于生产驱动上限（当前 12.4，由 Dockerfile 构建参数 `MAX_CUDA_RUNTIME` 在构建期校验，构建机无需 GPU）。12.8 驱动的开发/测试机可直接运行同一镜像，驱动向后兼容。
- 镜像不安装 CUDA toolkit，CUDA runtime 随 torch wheel 提供；宿主机只需满足驱动版本并安装 `nvidia-container-toolkit`。
- GPU 启动（不改变基础 compose，CPU 节点仍可直接启动）：

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
  ```

- `/{operatorId}/healthz` 的 `device` 是实际设备；`deviceRequested`、`cudaAvailable`、`gpuName`、`cudaRuntime`、`deviceFallbackReason` 说明请求值与回落原因。
- 权重解析：`WEIGHTS_DIR` > 本机/构建机模型仓（Windows `D:\models`、Linux `/models`，需含 `shared/`）> 镜像内 `weights/`。本机权重统一放 `D:\models\shared\<model>`，项目目录不放权重；构建镜像前执行 `python scripts/stage_weights.py` 把 `shared/` 暂存到 `operator/weights/` 并校验 SHA256SUMS。

## 模型网关后端（idg / siliconflow）

- 生产默认磐智（idg）签名网关，联调阶段用硅基流动平替。双后端配置在 `operator/model_gateway.py`，**启动时用环境变量切换，不改代码、不重建镜像**（compose 已透传）：

  ```bash
  python scripts/stage_weights.py                  # 构建前暂存权重并校验
  docker compose up -d --build                     # 默认磐智（idg）

  # 切硅基流动（联调）：
  MODEL_BACKEND=siliconflow SILICONFLOW_API_KEY=sk-xxx docker compose up -d

  # 切回磐智：
  MODEL_BACKEND=idg docker compose up -d
  ```

- 变量：`MODEL_BACKEND`（`idg` 默认 / `siliconflow`）、`MODEL_GATEWAY_BASE_URL` + `MODEL_APP_ID` + `MODEL_APP_KEY`（idg）、`SILICONFLOW_BASE_URL` + `SILICONFLOW_API_KEY`（siliconflow）。密钥一律启动时注入，不写进代码与镜像。**固定默认值已写入镜像 ENV**（`MODEL_BACKEND=idg`、`MODEL_APP_ID`、`SILICONFLOW_BASE_URL`）；可变项部署时注入，K8s 按 `- name: / value:` 依次添加（模板见 `deploy/k8s/op-data-mixing.yaml`）。
- `GET /health` 返回 `modelBackend`（后端名、凭据是否就绪、缺失变量），用于确认切换生效；通路验证用 `scripts/model_gateway_smoke.py`（默认跟随 `MODEL_BACKEND`）。
- 本机 GPU 开发使用已有 conda 环境（torch 2.9 + cu128，RTX 5060/sm_120）。**不要在该环境执行 `pip install -r requirements.txt`**：生产镜像钉的是 torch 2.6（cu124），执行后会降级 torch 并失去 50 系 GPU 支持；新增依赖时单独 `pip install <package>`。

## 算子清单

| 目录 | 中文名 | 阶段 | 优先级 | 职责 |
| --- | --- | --- | --- | --- |
| `dm-multimodal-analysis/` | 多模态识别与解析 | S1 | P0 | 模态判定；文本/图像/音频/视频解析；混合文件拆流 |
| `dm-corpus-normalization/` | 标准化、元数据与去重 | S1 | P0 | 标准容器、分区、manifest、元数据索引、去重、跨模态关联 |
| `dm-multimodal-labeling/` | 多模态自动打标 | S2 | P0 | 四模态打标，输出路径+置信度+证据 |
| `dm-taxonomy-labeling/` | 领域/能力多标签 | S2 | P1 | 领域 16 行业树、能力树多标签 |
| `dm-corpus-profiling/` | 规模、来源与领域画像 | S3 | P0 | 规模/分位数、六类来源+可信度、领域覆盖 |
| `dm-language-profiling/` | 语言、地域与时效画像 | S3 | P0 | 语种/方言、地域推断、时间抽取/新鲜度 |
| `dm-text-profiling/` | 文本属性与任务适配 | S3 | P0 | 句长/从句/被动/TTR/语体、六维任务适配 |
| `dm-quality-analysis/` | 质量、一致性与难度 | S3 | P0 | 完整率/冲突/基尼/标注覆盖、难度/正负样本 |
| `dm-speech-analysis/` | 语音质量与声学属性 | S3 | P1 | ASR、WER/CER、语速、基频、口音 |
| `dm-visual-analysis/` | 图像/视频属性 | S3 | P1 | 场景/目标/熵、镜头/光流/音画对齐/动作 |
| `dm-knowledge-analysis/` | 知识覆盖、热点与风格 | S3 | P1 | 实体/术语覆盖、知识密度、热点长尾、语体 |
| `dm-ratio-analysis/` | 配比分析与建议 | S4 | P1 | 能力预测、领域覆盖、推荐、补数、达成度、偏见 |
| `dm-dataset-packaging/` | 数据组装与打包 | S5 | P0 | 配额选样、成品 Parquet、manifest |
| `dm-ratio-reporting/` | 配比分析与报告 | S5 | P1 | 9 维聚合、报告数据包/渲染 |

## 权重

`weights/shared/<model>/` 放被 ≥2 个算子共用的模型；`weights/<operatorId>/` 只放单算子私有模型；算子目录内不再建 `weight/`。详见 [`docs/算子开发/权重目录约定.md`](../docs/算子开发/权重目录约定.md)。

S0 阶段全部 `core.run` 抛 `NotImplementedError("OPERATOR_NOT_IMPLEMENTED")`，不伪造任何结果；算法实现从 S1 起按任务卡落地。
