# FGW《数据配比》12.x / 13.x 追溯矩阵

> 日期：2026-11-17
> 口径：任务书附录 A、算子范围梳理第 7 节；证据路径以 S1～S6 已提交运行为准。
> 说明：平台职责（CRUD/UI/审核/任务状态/部署）不在算子范围，标注「平台」；人工确认项标注「人工」。

| 条款 | 能力/要求 | 算子 | 证据路径 | 状态 |
| --- | --- | --- | --- | --- |
| 12.1-1 | 数据源类型识别与六类归类 | OP-08 | `operator/dm-corpus-profiling/output/evidence/73e001cb4f8e5aed/` | 已实现/待评审 |
| 12.1-2 | 数据源-能力塑造知识库 | OP-16 | `operator/dm-ratio-analysis/output/evidence/d3cc21958ec443d6/` | 规则默认映射（Q-05 待人工） |
| 12.1-3 | 配比结构配置与占比计算 | OP-15 | `operator/dm-ratio-computation/output/evidence/cab32b6cd497cac3/` | 已实现/待评审 |
| 12.1-4/5 | 多方案生成与对标 | OP-16 / OP-19 | `operator/dm-ratio-analysis/.../d3cc21958ec443d6/`、`operator/dm-ratio-reporting/.../bf9ce91b0a82182b/` | 已实现/待评审 |
| 12.2-1/2 | 模态框架与类型树 | S0 基线 + OP-05/06 | `operator/baseline/tree-snapshot.json`（423/272/99 节点）、OP-05 `e53b5d9093388fe5` | 快照待 H-02 |
| 12.2-3/4/5 | 类型细分、唯一性、格式校验 | OP-05/06/07 | `operator/dm-multimodal-labeling/.../e53b5d9093388fe5/`、`operator/dm-label-governance/.../016129e87099395c/` | 已实现/待评审 |
| 12.2-6/8 | 自动打标与全模态覆盖 | OP-05 | `operator/dm-multimodal-labeling/.../e53b5d9093388fe5/` | 四模态均有输出 |
| 12.2-7 | 人工审核与修正 | 平台 + 人工 | `docs/交接文档/03-已完成功能与契约清单.md` | 范围外 |
| 12.2-9/10 | 一致性校验与质量统计 | OP-07 / OP-14 | `operator/dm-label-governance/.../016129e87099395c/`、`operator/dm-quality-analysis/.../f979e048a3250253/` | 已实现/待评审 |
| 12.3-1 | 三维配比配置（模态/来源/标签） | OP-15 | `operator/dm-ratio-computation/.../cab32b6cd497cac3/plan.json` | 已实现 |
| 12.3-2 | 标签级配比计算 | OP-15 | 同上 `result.jsonl` / `plan.json` | 已实现 |
| 12.3-3 | 高频核心标签占比 ≥30% | OP-15 | `.../cab32b6cd497cac3/validation.json` `core_label_coverage=0.5608` | 通过（小批次） |
| 12.3-4 | 一级/二级覆盖 100% | OP-15 | `validation.json` `level1=0.7333`/`level2=0.3772` | 小批次未达标，如实记录 |
| 12.3-5 | 动态迭代/薄弱标签 | OP-16 | `.../d3cc21958ec443d6/topup.json`、`recommendation.json` | 补数/增减 TopN 已实现 |
| 12.4-1/4 | 通用/专业权衡与建议模板 | OP-16 / OP-19 | `.../d3cc21958ec443d6/benchmark.json`、`.../bf9ce91b0a82182b/report_package.json` | 已实现/待评审 |
| 12.4-2/3 | 偏见检测与降权 | OP-16 | `.../d3cc21958ec443d6/capability.json` `bias` | 已实现；降权系数待 Q-04 |
| 12.4-5 | 配比影响评估 | OP-16 | `.../d3cc21958ec443d6/capability.json`、`benchmark.json` | 已实现（可解释映射） |
| 13.1-一 | 多模态接入与解析 | OP-01 | `operator/dm-multimodal-analysis/.../add117fbb422d09f/` | 已实现/待评审 |
| 13.1-二 | 标准化、分区、元数据、索引 | OP-02 | `operator/dm-corpus-normalization/.../10a342ae92595ab7/` | 已实现/待评审 |
| 13.1-三 | 主题聚类、来源分区、格式分组 | OP-03 | `operator/dm-text-clustering/.../e53b5d9093388fe5/` | 已实现/待评审 |
| 13.1-四 | 分层抽样 | OP-04 / OP-17 | `operator/dm-stratified-sampling/.../f7a8cdd04268386e/`、`operator/dm-dataset-packaging/.../347d6365d8457c91/` | 已实现/待评审 |
| 13.2-1 | 规模与格式统计 | OP-08 | `.../73e001cb4f8e5aed/metrics.json` `scale` | 已实现 |
| 13.2-2 | 来源分布与可信度 | OP-08 | 同上 `sourceDistribution`（AHP CR=0） | 已实现 |
| 13.2-3 | 领域分布与覆盖 | OP-08 | 同上 `domainCoverage` | 已实现 |
| 13.2-4 | 语种/方言识别 | OP-09 | `operator/dm-language-profiling/.../e53b5d9093388fe5/` | identified 426；方言待 H-03 |
| 13.2-5 | 地域推断 | OP-09 | 同上 `region.status=unavailable` | 地域库待人工 |
| 13.2-6 | 时间跨度与新鲜度 | OP-09 | 同上 `time`（新鲜度 0.137） | 已实现/阈值待 H-03 |
| 13.3-1 | 文本/语音/图像/视频属性 | OP-10/11/12 | `operator/dm-text-profiling/.../73e001cb4f8e5aed/`、`dm-speech-analysis/.../e53b5d9093388fe5/`、`dm-visual-analysis/.../e53b5d9093388fe5/` | 已实现/待评审 |
| 13.3-2 | 任务适配性评分 | OP-10 | `.../73e001cb4f8e5aed/metrics.json` `distributions` | 六维 p50 4.69 |
| 13.3-3 | 质量、一致性与难度 | OP-14 | `operator/dm-quality-analysis/.../f979e048a3250253/` | 已实现/待评审 |
| 13.3-4 | 知识覆盖、热点与风格 | OP-13 | `operator/dm-knowledge-analysis/.../e53b5d9093388fe5/` | 术语/KG unavailable（H-11） |
| 13.x 安全合规/版权 | 合规与版权检测 | OP-18 | `operator/dm-dataset-evaluation/.../020fe881d78849c0/` | 资源缺失 unavailable（Q-08） |
| 13.x 图谱/向量索引 | 图谱构建与向量检索 | OP-20 | `operator/dm-graph-indexing/.../e5f5df6ab0857e5f/` | 已实现；服务待 Q-07 |
| 13.x 专家校验 | 专家抽样与一致性 | OP-21 | `operator/dm-expert-validation/.../8ea8159784975ebe/` | 专家标注 blocked（H-05） |
| 13.x 风险分级 | 指标规则风险检测 | OP-22 | `operator/dm-risk-detection/.../8a156871249e49f4/` | 已实现/待评审 |
| 12.4-6 / 13.4 | 平台 CRUD、报告下载、工单、任务状态 | 平台 | `docs/交接文档/02-环境部署与算子池配置.md` | 范围外 |

## 追溯说明

1. 每行证据均指向真实运行目录；`verification.json` 校验 runId/版本/产物哈希。
2. 标「待人工」的条款不改变算子实现状态，只影响效果验收（H-02/H-03/H-05/H-11/Q-07/Q-08）。
3. 平台职责不写入算子，符合任务书 1.3「明确不在范围」。
