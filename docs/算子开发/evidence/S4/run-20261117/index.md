# S4 阶段证据索引 · 配比引擎

> 日期：2026-11-17
> 上游：OP-02 `operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`、OP-05 `operator/runtime/transport/output/dm-multimodal-labeling/e53b5d9093388fe5`

| 算子 | runId | 证据目录 | 关键指标 |
| --- | --- | --- | --- |
| OP-15 配比引擎 | cab32b6cd497cac3 | `operator/dm-ratio-computation/output/evidence/cab32b6cd497cac3/` | 标签 66；合计 1.0；检查 3/6；缺口 99722 |
| OP-16 配比分析与建议 | d3cc21958ec443d6 | `operator/dm-ratio-analysis/output/evidence/d3cc21958ec443d6/` | 达成度 0.7413773333→0.7629384951；约束 3/3；补数缺口 99722；对标 balanced |

## 门禁核对（OP-15）

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 权重链路写入 README 可复算 | 通过 | `operator/dm-ratio-computation/README.md` 第 2 节 |
| 最大余数法误差 ≤0.1% | 通过 | `metrics.normalizationError` |
| 校验单含实测值/阈值/来源 | 通过 | `validation.json` |
| 10 条样本极限用例 | 通过 | `tests/test_op15.py::test_core_ten_sample_extreme` |
| 核心 ≥30%/一级二级 100%/最小样本 10 万 | 如实记录 | 小批次必然不达标，见 `validation.json`（不调阈值凑通过） |

## 门禁核对（OP-16）

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 能力贡献可加总 | 通过 | `capability.json` contributions；`tests/test_op16.py::test_capability_contributions_sum` |
| 建议满足约束且改动量可解释 | 通过 | `recommendation.json` 约束单 + Top10 增减 |
| 补数按真实库存 | 通过 | `topup.json` gap = 建议投喂 − 库存 |
| 达成度 = 目标 vs 实际 | 通过 | `capability.json` achievement |
| 偏见/对标可复算 | 通过 | `tests/test_op16.py` 手工对拍 |
| 无硬编码 fit 向量 | 通过 | 映射来自 FGW 12.1，逐来源权重写入 `analysis.json` |

## 待补

- 权威能力/领域映射库（Q-05）、目标能力模板（H-12）、权重与阈值（Q-04/H-03）待人工确认。
- Docker 构建与容器内探针（H-01）待人工；按 10.2 第 5 条不阻断 S5。
- 小批次下覆盖率与库存缺口未达标，如实记录，不调阈值凑通过。
