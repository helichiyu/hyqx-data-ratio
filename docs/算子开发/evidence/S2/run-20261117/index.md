# S2 阶段证据索引 · 分片与打标（OP-03 / OP-05 / OP-06 / OP-07）

> 日期：2026-11-17
> 上游：S1 OP-02 运行目录 `operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`（432 条标准记录）
> 链路：`OP-02 产物 → OP-03 predict → OP-05 predict → OP-06 predict → OP-07 predict`（统一 HTTP 入口）
> 运行命令：`"D:/anaconda3/envs/use/python.exe" scripts/run_s2_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"`

## 1. 运行结果

| 算子 | runId | 证据目录 | 样本/成功/失败 | 关键指标 |
| --- | --- | --- | --- | --- |
| OP-03 句向量与主题聚类 | e53b5d9093388fe5 | `operator/dm-text-clustering/output/evidence/e53b5d9093388fe5/` | 426/426/0 | 768 维；K=15；轮廓 0.0476；簇 15 个；488 chunks |
| OP-05 多模态自动打标 | e53b5d9093388fe5 | `operator/dm-multimodal-labeling/output/evidence/e53b5d9093388fe5/` | 432/278/154 | 打标 278（{'audio': 1, 'image': 1, 'text': 275, 'video': 1}）；未归类 154；路径合法率 1.0 |
| OP-06 领域/能力多标签 | e53b5d9093388fe5 | `operator/dm-taxonomy-labeling/output/evidence/e53b5d9093388fe5/` | 426/420/6 | 领域叶子 209 / 能力叶子 65；命中 领域 382 / 能力 400；路径合法率 1.0 |
| OP-07 标签治理 | 016129e87099395c | `operator/dm-label-governance/output/evidence/016129e87099395c/` | 432/432/0 | 标签 278；非法 0；冲突 0；未归类 154；审核指标 null |

## 2. S2 门禁核对

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| OP-03 固定 seed 可复现，向量维度/模型版本写入结果 | 通过 | OP-03 `metrics.json`：`deterministic=true`、`vectorDimension=768`、`modelVersion=bge-base-zh-v1.5`；测试断言重跑 `result.jsonl` 哈希一致 |
| OP-05 四模态均跑通，不是只做文本 | 通过 | OP-05 `labeledCounts`/`evidenceSources`：text 426、image 1、audio 3、video 2 均有证据路径与输出 |
| 打标路径 100% 命中当前 `treeVersion` | 通过 | OP-05/OP-06 `pathLegalRate=1.0`；`treeVersion=taxonomy-1013-pending`（H-02） |
| 低置信/冲突进未归类池，规则可复算 | 通过 | OP-05 `unclassified.jsonl` + `failures.jsonl`；OP-07 `unclassifiedByReason` |
| 与人工标注比对（样本量/准确率/区间/混淆矩阵） | 待人工 | 无真值（H-05），`annotation.accuracy=null` + `blockedReason`，不编造 |
| OP-06 领域/能力两个标签空间分离（P1） | 通过 | OP-06 `spacesSeparated=true`、`labelSpaceSizes` 双空间 |
| OP-07 治理指标来自真实记录（P1） | 通过 | `reviewMetrics` 全 `null` + `REVIEW_RECORDS_REQUIRED`；其余指标来自真实打标结果 |
| 标签树版本变更时旧结果可追溯 | 通过 | 结果全部写 `treeVersion`，不做静默改写 |

## 3. 未完成/待人工项

| 项 | 影响 | 处理 |
| --- | --- | --- |
| 人工标注比对（准确率/Wilson/混淆矩阵） | S2 效果验收 | H-05；写 `null` + `blockedReason` |
| `treeVersion` 权威源确认 | 路径合法性口径 | H-02；当前 `taxonomy-1013-pending` |
| 模型许可证审批（bge-base MIT / paraformer Apache-2.0 / RapidOCR Apache-2.0） | 入镜像 | H-06 待人工 |
| Docker 构建 / 容器内探针 | S0/S2 人工门禁 | H-01 待人工；按任务书 10.2 第 5 条不阻断开发 |

## 4. 复算

```bash
# 重跑整条 S2 链路并重建四个算子证据目录
"D:/anaconda3/envs/use/python.exe" scripts/run_s2_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 5. 说明

- OP-03/OP-05/OP-06 的 runId 由「输入指纹 + 算子版本 + 参数哈希 + seed」决定，不同算子可能相同；证据按算子目录隔离，不影响追溯。
- 全部产物可复算：固定 seed=42、固定模型版本与树版本，重跑覆盖同一 runId 目录。
