# S3 阶段证据索引 · 画像与抽样（OP-08/09/10/14/04/11/12/13）

> 日期：2026-11-17
> 上游：OP-02 运行目录 `operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`（432 条标准记录）
> 运行命令：`"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"`

## 1. 运行结果

| 算子 | runId | 证据目录 | 样本/成功/失败 | 关键指标 |
| --- | --- | --- | --- | --- |
| OP-08 规模、来源与领域画像 | 73e001cb4f8e5aed | `operator/dm-corpus-profiling/output/evidence/73e001cb4f8e5aed/` | 432/432/0 | 432 条；字符 188345；六类合计 100.0%；CR 0.0 |
| OP-09 语言、地域与时效画像 | e53b5d9093388fe5 | `operator/dm-language-profiling/output/evidence/e53b5d9093388fe5/` | 432/432/0 | identified 426；置信度均值 0.986111；新鲜度 0.136546 |
| OP-10 文本属性与任务适配 | 73e001cb4f8e5aed | `operator/dm-text-profiling/output/evidence/73e001cb4f8e5aed/` | 426/426/0 | overall p50 4.688256；低适配 4 |
| OP-14 质量、一致性与难度 | f979e048a3250253 | `operator/dm-quality-analysis/output/evidence/f979e048a3250253/` | 432/432/0 | 完整率 1.0；近重复组 4；低质量 0 |
| OP-04 分层抽样 | f7a8cdd04268386e | `operator/dm-stratified-sampling/output/evidence/f7a8cdd04268386e/` | 432/86/0 | 目标 86；实抽 86；最大偏差 0.085486；未达标层 0 |
| OP-11 语音质量与声学属性 | e53b5d9093388fe5 | `operator/dm-speech-analysis/output/evidence/e53b5d9093388fe5/` | 3/3/0 | 音频 3；转写 2；WER unavailable；低质量 1 |
| OP-12 图像/视频属性 | e53b5d9093388fe5 | `operator/dm-visual-analysis/output/evidence/e53b5d9093388fe5/` | 3/3/0 | 图像熵 1.947062；动态帧占比 0.921053 |
| OP-13 知识覆盖、热点与风格 | e53b5d9093388fe5 | `operator/dm-knowledge-analysis/output/evidence/e53b5d9093388fe5/` | 426/426/0 | 语体 2 类；术语 unavailable；热点 {'hot': 15, 'long_tail': 234, 'unknown': 177} |

## 2. S3 门禁核对

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 每项指标有口径、样本量、分布/分位数 | 通过 | 各算子 `metrics.json` + README 口径 |
| 全部指标来自 OP-02 标准产物 | 通过 | 链路 input 均为 OP-02 运行目录；标签类只读 OP-05/06 结果文件 |
| 同批次重跑结果一致 | 部分通过 | 规则/统计类幂等；OP-11 ASR 标 `deterministic=false` |
| 低质量/低适配/缺口/未识别清单可下钻 | 通过 | `low_quality.jsonl`、`low_fit.jsonl`、`unmetStrata`、`reasonCode` |
| 画像结果可被 OP-15 消费 | 通过 | 来源/领域/质量/标签字段齐全（见各 result.jsonl） |
| OP-04 配额/实抽/偏差可复算 | 通过 | `quota_table.json` |
| OP-11/12/13 在真实样例上给出指标 | 通过 | 语音 3 条、图像 1/视频 2、文本 426 |
| P0/P1 共用同一批标准产物与 `treeVersion` | 通过 | 全部 `treeVersion=taxonomy-1013-pending`（H-02） |

## 3. 未完成/待人工项

| 项 | 影响 | 处理 |
| --- | --- | --- |
| 阈值口径书面确认（分位数/新鲜度/基尼/WER/抽样比例） | S3 效果口径 | H-03；已标 `provisional` |
| 人工标注与专家结果 | 效果验收 | H-05；不编造准确率 |
| 模型/权重许可（paraformer 等） | 入镜像 | H-06 |
| Docker 构建/容器探针 | 阶段门禁 | H-01；按 10.2 第 5 条不阻断 |

## 4. 复算

```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```
