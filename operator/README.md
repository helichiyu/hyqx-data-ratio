# 算子目录

每个算子一个目录，目录名即算子英文名（`dm-<对象>-<动作>`）。当前为目录占位，具体实现按 `docs/算子开发/【算子清单】数据配比中心算子开发清单_2026-11-16.xlsx` 的契约落地。

| 目录 | 中文名 | 优先级 | 职责 |
| --- | --- | --- | --- |
| `dm-multimodal-analysis/` | 多模态识别与解析 | P0 | 模态判定；文本/图像/音频/视频解析；混合文件拆流 |
| `dm-corpus-normalization/` | 标准化、元数据与去重 | P0 | 标准容器、分区、manifest、元数据索引、去重、跨模态关联 |
| `dm-text-clustering/` | 句向量与主题聚类 | P0 | bge 句向量、K-Means、轮廓系数选 K、簇主题词 |
| `dm-stratified-sampling/` | 分层抽样 | P1 | Neyman 配额、分层抽样、代表性校验 |
| `dm-multimodal-labeling/` | 多模态自动打标 | P0 | 文本/图像/音频/视频四模态打标，输出路径+置信度 |
| `dm-taxonomy-labeling/` | 领域/能力多标签 | P1 | 领域 16 行业树、能力树多标签 |
| `dm-label-governance/` | 标签治理 | P1 | 标签校验、未归类识别、质量评估、治理属性建议 |
| `dm-corpus-profiling/` | 规模、来源与领域画像 | P0 | 规模/分位数、六类来源+可信度、领域覆盖 |
| `dm-language-profiling/` | 语言、地域与时效画像 | P0 | 语种/方言、地域推断、时间抽取/新鲜度 |
| `dm-text-profiling/` | 文本属性与任务适配 | P0 | 句长/从句/被动/TTR/语体、六维任务适配 |
| `dm-speech-analysis/` | 语音质量与声学属性 | P1 | ASR、WER/CER、语速、基频、口音 |
| `dm-visual-analysis/` | 图像/视频属性 | P1 | 场景/目标/熵、镜头/光流/音画对齐/动作 |
| `dm-knowledge-analysis/` | 知识覆盖、热点与风格 | P1 | 实体/术语/知识密度/层次、热点长尾/语体 |
| `dm-quality-analysis/` | 质量、一致性与难度 | P0 | 完整率/冲突/基尼/标注覆盖、难度/正负样本 |
| `dm-ratio-computation/` | 配比引擎 | P0 | 六类来源占比、加权配比、归一化、30%/100%/库存校验 |
| `dm-ratio-analysis/` | 配比分析与建议 | P1 | 能力预测、领域覆盖、推荐、补数、达成度、偏见、对标 |
| `dm-dataset-packaging/` | 数据组装与打包 | P0 | 配额选样、成品 Parquet、manifest |
| `dm-dataset-evaluation/` | 数据评测 | P0 | 抽样、标签准确率、合规/版权、综合质量分 |
| `dm-ratio-reporting/` | 配比分析与报告 | P1 | 9 维聚合、报告数据包/渲染 |
| `dm-graph-indexing/` | 知识图谱与向量索引 | P1 | NER/RE/Neo4j、多模态 embedding/FAISS |
| `dm-expert-validation/` | 专家校验 | P1 | 5-10% 抽样、Kappa/Alpha、准确率 |
| `dm-risk-detection/` | 风险检测与分级 | P1 | 阈值/趋势/去重/抑制、过时知识 |
