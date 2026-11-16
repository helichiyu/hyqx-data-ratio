# S1 阶段证据索引 · 接入与标准化（OP-01 / OP-02）

> 日期：2026-11-16
> 批次：`docs/算子开发/samples/mixed/full_batch_2026-11-16.zip`（5,809,543 B，SHA-256 `46f6c46edfe331db81375dbebd9e0036fe0db40372c8315774332eafca11bd23`）
> 链路：`uploadFile → OP-01 predict → downloadFile → OP-02 predict（inputFile=OP-01 runDir）`
> 运行命令：`"D:/anaconda3/envs/use/python.exe" scripts/run_s1_chain.py --batch "docs/算子开发/samples/mixed/full_batch_2026-11-16.zip"`

## 1. 运行结果

| 项 | OP-01 多模态识别与解析 | OP-02 标准化、元数据与去重 |
| --- | --- | --- |
| runId | `add117fbb422d09f` | `10a342ae92595ab7` |
| 证据目录 | [`operator/dm-multimodal-analysis/output/evidence/add117fbb422d09f/`](../../../../operator/dm-multimodal-analysis/output/evidence/add117fbb422d09f/report.md) | [`operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7/`](../../../../operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7/report.md) |
| sampleCount | 432 | 432 |
| successCount | 432 | 432 |
| failedCount | 0 | 0 |
| 模态计数 | text 426 / image 1 / audio 3 / video 2 | 同左，全部标准化 |
| 关键产物 | `result.jsonl`、`manifest.json`、`metrics.json`、`split_manifest.json`、`streams/` | 7 个 Parquet 分区（432 行）、WebP 1、WAV 3、MP4 2、`index/metadata.parquet`、重复/异常/关联清单 |

## 2. S1 门禁核对

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 真实混合批次含文本、图像、音频、视频、带音轨视频、PDF 扫描页 | 通过 | OP-01 `modalCounts`；PDF 326 页 / 扫描页 106 / 空文本页 86 |
| 每文件有 `modal`、`confidence`、命中证据；低置信进待确认 | 通过 | OP-01 `result.jsonl` 每条 `metadata.extra.detection`；低置信 0、冲突 0 |
| 四模态失败率、空文本率、乱码率、解码失败数真实统计 | 通过 | OP-01 `metrics.text` / `metrics.pdf` / `failures.jsonl`（0 失败） |
| 标准产物可被下游直接读取 | 通过 | OP-02 Parquet 写后回读 432 行；WebP/WAV/MP4 抽检可解码 |
| manifest 条数/字节/哈希与实际文件一致 | 通过 | 两个算子 `manifest.json.artifacts[]` 与 `artifacts.sha256` |
| 同一输入重跑落到同一路径，结果一致 | 通过 | HTTP 层 runId 缓存；单元/端到端测试断言 `result.jsonl` 哈希一致 |
| 无平台职责外溢 | 通过 | 仅计算与产物，无数据库/UI/任务状态 |

## 3. 未完成/待人工项

| 项 | 影响 | 处理 |
| --- | --- | --- |
| 与人工标注比对（模态/属性准确率、打标准确率） | S1 效果验收 | 无人工真值（H-05）；报告中写 `null` + `blockedReason`，不编造 |
| OCR 后端 | PDF 扫描页文本 | 本站无 OCR 引擎；扫描页只统计并标 `OCR_BACKEND_UNAVAILABLE` |
| Docker 构建 / 容器内 22 healthz / 压缩包独立构建 | S0/S1 人工门禁 | H-01 待人工；按任务书 10.2 第 5 条不阻断开发 |
| 阈值口径（`dt` 来源、去重距离、VAD 阈值） | 结果稳定性 | 使用 `baseline/thresholds.json` / 算子 `configs/*.json` 联调初值，结果标 `provisional` |

## 4. 测试

```text
pytest operator/dm-corpus-normalization/tests operator/dm-multimodal-analysis/tests tests operator/_template/tests -q
86 passed, 1 skipped（Windows 无符号链接权限）
```

覆盖：22 个算子五端点（已实现算子期望成功、骨架期望 `OPERATOR_NOT_IMPLEMENTED`）、路径越界、zip-slip、超大文件、幂等；OP-01 四模态/PDF/混合 zip/失败原因/Schema/幂等；OP-02 消费真实上游、Parquet 回读、去重、异常、关联、幂等、manifest 对账。

## 5. 复算

```bash
# 重跑整条 S1 链路并重建两个算子证据目录
"D:/anaconda3/envs/use/python.exe" scripts/run_s1_chain.py \
  --batch "docs/算子开发/samples/mixed/full_batch_2026-11-16.zip"

# 单算子复算（不经过 HTTP）
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
op1 = inference._import_operator_core("dm-multimodal-analysis")
op2 = inference._import_operator_core("dm-corpus-normalization")
r1 = op1.run("docs/算子开发/samples/mixed/full_batch_2026-11-16.zip", {}, 42, "operator/runtime/output/manual-op01")
r2 = op2.run(r1["outputDir"], {}, 42, "operator/runtime/output/manual-op02")
print(r1["runId"], r1["sampleCount"], r1["successCount"], r1["failedCount"])
print(r2["runId"], r2["sampleCount"], r2["successCount"], r2["failedCount"])
PY
```
