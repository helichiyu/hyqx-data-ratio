# OP-18 数据评测（`dm-dataset-evaluation`）

- 语义编码：`prod_evaluation_v1`
- 阶段/优先级：S5 / P0
- 版本：`0.1.1`
- 模型：复用 OP-05 打标模型（不自带权重）

## 1. 用途与边界

**做**：消费 OP-17 成品 manifest/Parquet，按 5%–10% 固定 seed 分层抽样；
有真值时输出总体/分模态准确率、前缀准确率、宏 F1、混淆矩阵、错标清单；
无真值时如实输出 `null` + `blockedReason`，并给出代理指标；
检测合规词表/版权哈希；聚合综合质量分。

**不做**：不重新打标、不改上游标签；不生成真值；不做平台审核流程；
不把代理指标冒充准确率；资源缺失时不编造合规结果。

## 2. 抽样与指标口径

```text
按模态分层；每层按 sha256(seed|record_id) 升序
每层抽样数 = max(minPerModal, ceil(层记录数 × ratio))，ratio 默认 0.1
精确准确率 = 预测完整路径 == 真值完整路径
前缀准确率 = 预测与真值互为路径前缀
宏 F1 = 真值标签集合上单标签 P/R/F1 的宏平均
混淆矩阵 = (真值, 预测) 计数；真值频次 TopK 之外归 OTHER
```

- 无真值：`accuracy/prefixAccuracy/macroF1/confusion = null`，`blockedReason=TRUTH_REQUIRED`；
- 代理指标（`proxy=true`）：路径合法率、平均/中位置信度、低置信占比、完整率、空文本率；
- 合规：命中 = 正文包含敏感词或记录 SHA-256/MD5 命中版权库；资源缺失 `unavailable`；
- 原创性：自研代理（语料内近重复，字符 n-gram Jaccard；原创性分 = 1 - 近重复率；Q-08 2026-11-18），独立报告不计入综合分；
- 综合分 = Σ 可用分项×权重 / Σ 可用权重；不可用分项剔除而不是按 0 计；
  无真值时 `score.scope=proxy_only`，等级加 `proxy_` 前缀（如 `proxy_excellent`），避免被误读为效果评测；
  权重与分级见 `configs/evaluation.json`（联调初值，H-03）。

## 3. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `input_path` | 必填 | OP-17 运行目录（`manifest.json` + `dataset/**/*.parquet`） |
| `params.ratio` | 0.1 | 抽样比例（5%–10%；越界钳制到 1%–100%） |
| `params.truth_path` | 无 | 真值 JSONL（`record_id` + `path`/`label`），须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |
| `params.labels_path` | 无 | OP-05 运行目录；用于校验模型/树版本一致，不一致直接阻断 |
| `params.compliance_terms_path` | 无 | 敏感词表（JSON 数组或每行一词） |
| `params.copyright_hashes_path` | 无 | 版权哈希库（JSON 数组或每行一个 SHA-256/MD5） |

## 4. 运行与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-dataset-evaluation/tests
```

样例：先运行 OP-17 样例生成成品，再把其输出目录作为本算子 `input_path`
（见 `dataset/DATA_SCHEMA.md`）。

## 5. 已知限制

1. H-05 真值未提供时，效果指标为 `null`；代理指标只反映合法性与完整性；
2. 合规词表/版权库未提供时 `unavailable`，不计入综合分；
3. 混淆矩阵对 TopK 之外标签归 OTHER，完整矩阵需平台下钻；
4. 评测模型/树版本由 OP-17 从 OP-05 透传；传入不同版本的 `labels_path` 会被阻断。

## 6. 版本与证据

`operatorVersion=0.1.1`、`modelVersion/treeVersion` 继承 OP-05、`paramsHash` 入 manifest/metrics；
证据目录 `operator/dm-dataset-evaluation/output/evidence/<runId>/`。
