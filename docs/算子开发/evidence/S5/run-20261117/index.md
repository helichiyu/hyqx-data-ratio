# S5 阶段证据索引 · 生产评测

> 日期：2026-11-17
> 上游：OP-15 `operator/runtime/transport/output/dm-ratio-computation/cab32b6cd497cac3`；OP-05/07/08/09/10/14 复用 S2/S3 运行目录

| 算子 | runId | 证据目录 | 关键指标 |
| --- | --- | --- | --- |
| OP-17 数据组装与打包 | 347d6365d8457c91 | `operator/dm-dataset-packaging/output/evidence/347d6365d8457c91/` | 选样 278/100000；分片 7；行 278；重复 0；缺口 99722 |
| OP-18 数据评测 | 020fe881d78849c0 | `operator/dm-dataset-evaluation/output/evidence/020fe881d78849c0/` | 抽样 31；真值 unavailable；路径合法率 1.0；综合分 1.0（proxy_only） |
| OP-19 配比分析与报告 | bf9ce91b0a82182b | `operator/dm-ratio-reporting/output/evidence/bf9ce91b0a82182b/` | 九维可用 9/9；综合 0.6889305599（pass）；渲染 ok |

## 门禁核对（OP-17）

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 选样数=配额 | 如实记录 | 库存 278 < 配额 10 万，`quota.json` 逐标签记录缺口 |
| 无重复 | 通过 | `metrics.duplicateRecords=0` |
| manifest 条数/字节/哈希与文件一致 | 通过 | `manifest.json` 逐文件 rows/bytes/MD5/SHA-256；测试对账 |
| 下游可读 Parquet | 通过 | `tests/test_op17.py` 用 pyarrow 读取 |
| 固定 seed 幂等/续跑 | 通过 | `tests/test_op17.py` 确定性与断点续跑 |

## 门禁核对（OP-18）

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 抽样 5–10% 可复现 | 通过 | `evaluation.json.sampling`；固定 seed |
| 准确率/F1/混淆矩阵 | 无真值 | `truth.status=unavailable`，`blockedReason=TRUTH_REQUIRED` |
| 模型/树版本与 OP-05 一致 | 通过 | `versionCheck`（labels_path 校验） |
| 合规证据可下钻 | 资源缺失 | `compliance.status=unavailable`（Q-08） |

## 门禁核对（OP-19）

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 九维全部来自真实算子输出 | 通过 | `report_package.json` dimensions 引用各算子 metrics |
| 阈值/权重有来源 | 通过 | `configs/reporting.json` + 联调初值说明 |
| 报告数据包字段齐全 | 通过 | `report_package.json` / `status_matrix.json` / `conclusions.jsonl` |
| 渲染失败不影响数据包 | 通过 | `tests/test_op19.py::test_render_failure_does_not_break_package` |

## 待补

- 真值/专家标注（H-05）、合规词表/版权库（Q-08）、九维权重/阈值（H-03）待人工确认。
- Docker 构建与容器内探针（H-01）待人工；按 10.2 第 5 条不阻断 S6。
- 小批次库存不足导致实抽远低于 10 万配额，如实记录。
