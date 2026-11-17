# S6 阶段证据索引 · 工具与风险

> 日期：2026-11-17
> 上游：OP-02 `operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`、OP-03 `operator/runtime/transport/output/dm-text-clustering/e53b5d9093388fe5`、OP-05 `operator/runtime/transport/output/dm-multimodal-labeling/e53b5d9093388fe5`；OP-08～19 复用 S3/S4/S5 运行目录

| 算子 | runId | 证据目录 | 关键指标 |
| --- | --- | --- | --- |
| OP-20 知识图谱与向量索引 | e5f5df6ab0857e5f | `operator/dm-graph-indexing/output/evidence/e5f5df6ab0857e5f/` | 节点 1309；边 6232；向量 426；recall@10 0.875；服务 unavailable |
| OP-21 专家校验 | 8ea8159784975ebe | `operator/dm-expert-validation/output/evidence/8ea8159784975ebe/` | 总体 278；实抽 28；一致性 blocked；争议 None |
| OP-22 风险检测与分级 | 8a156871249e49f4 | `operator/dm-risk-detection/output/evidence/8a156871249e49f4/` | 风险 4（critical 2）；抑制 0；过时 unavailable |

## 门禁核对（OP-20）

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 实体/关系计数一致 | 通过 | `graph_stats.json` 与 nodes/edges 文件；测试对账 |
| 图谱导入文件可解析 | 通过 | `neo4j_import.cypher` / JSONL；测试读取 |
| 索引重建幂等/检索可复现 | 通过 | `index/meta.json` indexVersion；两次运行一致 |
| 服务不可用有明确失败码 | 通过 | `metrics.services.*.reasonCode=SERVICE_NOT_CONFIGURED` |

## 门禁核对（OP-21）

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 抽样 5–10% 可复现 | 通过 | `sampled.jsonl`；固定 seed |
| 高风险必选 | 机制通过/实数据无风险输入 | 单测覆盖；真实链路未提供 record 级风险 |
| Kappa/Alpha 用真实标注 | 无专家数据 | `agreement.status=blocked`（H-05） |
| 争议可下钻 | 机制通过 | `disputes.jsonl`；单测覆盖 |

## 门禁核对（OP-22）

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 规则命中/未命中可复算 | 通过 | `risks.jsonl` + `risk_report.json` |
| 双阈值/最小样本生效 | 通过 | 单测 `test_op22.py` |
| 去重/抑制可解释 | 通过 | `suppressed` + 单测 |
| 证据引用指标结果 | 通过 | `evidence.metricsPath/metric/value` |
| 过时检测有知识库来源 | 缺失 | `outdated.status=unavailable`（H-11） |

## 待补

- 本体/KG/词表（H-11）、专家标注（H-05）、风险阈值（H-03）、Neo4j/FAISS（Q-07）待人工。
- Docker 构建与容器内探针（H-01）待人工；按 10.2 第 5 条不阻断 S7。
