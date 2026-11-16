# 算子工程目录（单镜像 `op-data-mixing`）

**本目录是唯一的 Docker 构建上下文。** 22 个算子共用根 `inference.py`、`map.json`、`requirements.txt` 与同一个镜像/容器，不按算子拆镜像、不按算子另起端口。

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

# 从仓库根验证 22 个探针
python scripts/check_healthz.py --base-url http://127.0.0.1:17025

# 契约测试（仓库根）
python -m pytest tests operator/_template/tests

# 单镜像
docker build -t op-data-mixing:0.1.0 .
docker compose up -d
```

协议、错误码、路径闸门、幂等与 Schema 见 [`docs/算子开发/算子工程契约.md`](../docs/算子开发/算子工程契约.md)。

## 算子清单

| 目录 | 中文名 | 阶段 | 优先级 | 职责 |
| --- | --- | --- | --- | --- |
| `dm-multimodal-analysis/` | 多模态识别与解析 | S1 | P0 | 模态判定；文本/图像/音频/视频解析；混合文件拆流 |
| `dm-corpus-normalization/` | 标准化、元数据与去重 | S1 | P0 | 标准容器、分区、manifest、元数据索引、去重、跨模态关联 |
| `dm-text-clustering/` | 句向量与主题聚类 | S2 | P0 | bge 句向量、K-Means、轮廓系数选 K、簇主题词 |
| `dm-multimodal-labeling/` | 多模态自动打标 | S2 | P0 | 四模态打标，输出路径+置信度+证据 |
| `dm-taxonomy-labeling/` | 领域/能力多标签 | S2 | P1 | 领域 16 行业树、能力树多标签 |
| `dm-label-governance/` | 标签治理 | S2 | P1 | 标签校验、未归类识别、质量评估、治理建议 |
| `dm-corpus-profiling/` | 规模、来源与领域画像 | S3 | P0 | 规模/分位数、六类来源+可信度、领域覆盖 |
| `dm-language-profiling/` | 语言、地域与时效画像 | S3 | P0 | 语种/方言、地域推断、时间抽取/新鲜度 |
| `dm-text-profiling/` | 文本属性与任务适配 | S3 | P0 | 句长/从句/被动/TTR/语体、六维任务适配 |
| `dm-quality-analysis/` | 质量、一致性与难度 | S3 | P0 | 完整率/冲突/基尼/标注覆盖、难度/正负样本 |
| `dm-stratified-sampling/` | 分层抽样 | S3 | P1 | Neyman 配额、分层抽样、代表性校验 |
| `dm-speech-analysis/` | 语音质量与声学属性 | S3 | P1 | ASR、WER/CER、语速、基频、口音 |
| `dm-visual-analysis/` | 图像/视频属性 | S3 | P1 | 场景/目标/熵、镜头/光流/音画对齐/动作 |
| `dm-knowledge-analysis/` | 知识覆盖、热点与风格 | S3 | P1 | 实体/术语覆盖、知识密度、热点长尾、语体 |
| `dm-ratio-computation/` | 配比引擎 | S4 | P0 | 六类来源占比、加权配比、归一化、校验 |
| `dm-ratio-analysis/` | 配比分析与建议 | S4 | P1 | 能力预测、领域覆盖、推荐、补数、达成度、偏见 |
| `dm-dataset-packaging/` | 数据组装与打包 | S5 | P0 | 配额选样、成品 Parquet、manifest |
| `dm-dataset-evaluation/` | 数据评测 | S5 | P0 | 抽样、标签准确率、合规/版权、综合质量分 |
| `dm-ratio-reporting/` | 配比分析与报告 | S5 | P1 | 9 维聚合、报告数据包/渲染 |
| `dm-graph-indexing/` | 知识图谱与向量索引 | S6 | P1 | NER/RE/Neo4j、多模态 embedding/FAISS |
| `dm-expert-validation/` | 专家校验 | S6 | P1 | 5-10% 抽样、Kappa/Alpha、准确率 |
| `dm-risk-detection/` | 风险检测与分级 | S6 | P1 | 阈值/趋势/去重/抑制、过时知识 |

## 权重

`weights/shared/<model>/` 放被 ≥2 个算子共用的模型；`weights/<operatorId>/` 只放单算子私有模型；算子目录内不再建 `weight/`。详见 [`docs/算子开发/权重目录约定.md`](../docs/算子开发/权重目录约定.md)。

S0 阶段全部 `core.run` 抛 `NotImplementedError("OPERATOR_NOT_IMPLEMENTED")`，不伪造任何结果；算法实现从 S1 起按任务卡落地。
