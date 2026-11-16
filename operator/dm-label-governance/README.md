# OP-07 标签治理（`dm-label-governance`）

- 语义编码：`corpus_label_governance_v1`
- 阶段/优先级：S2 / P1
- 版本：`0.1.0`
- 依赖：OP-05/OP-06 标签结果、树快照、可选人工审核记录（当前无）

## 1. 用途与边界

**用途**：校验标签合法性、识别未归类原因、检测重复/跨领域冲突、提示低置信与 PII，输出质量报告与治理建议。

**做**：

- 树快照校验（内容/领域/能力三空间并集），非法路径给出编辑距离 ≤3 的最近节点建议；
- 重复路径、同记录不同一级类目的高置信冲突；
- 低置信（<0.25）提示；
- PII 正则扫描（邮箱/手机号/身份证/银行卡），只提示并脱敏展示，不改数据；
- 未归类原因汇总；治理建议带命中依据。

**不做**：

- 不自动修改标签、不入库、不派发审核任务；
- 无人工审核记录时不计算 Kappa/Alpha/准确率/采纳率（`null` + `blockedReason`）；
- 不做模型推理（`requiresWeights=false`）。

## 2. 接口与参数

`input_path` 接受 OP-05/OP-06 运行目录（含 `result.jsonl`）或结果文件。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `min_confidence` | 0.25 | 低置信阈值 |
| `pii_enabled` | true | 是否扫描 PII |
| `max_records` | 100000 | 最多记录数 |

支持三种标签字段：`labels`（OP-05）、`domainLabels` / `abilityLabels`（OP-06）。

## 3. 输出

```text
result.jsonl          # 逐记录：legal、issues（含建议）、conflicts、pii、unclassified
illegal.jsonl         # 非法路径与最近节点建议
conflicts.jsonl       # DUPLICATE_PATH / CROSS_DOMAIN_CONFLICT
pii.jsonl             # 脱敏命中
unclassified.jsonl    # 未归类原因
governance_report.json# 汇总 + 治理建议 + reviewMetrics(null)
metrics.json / manifest.json / failures.jsonl / input_manifest.json / summary.json
```

## 4. 指标口径

- `legalRate` =（标签总数 - 非法标签数）/ 标签总数；
- `conflicts`：重复路径 + 跨一级类目高置信冲突；
- `piiRecords`：命中任一 PII 规则的记录数（展示脱敏值）；
- `reviewMetrics.kappa/alpha/accuracy/adoptionRate/modificationRate`：无审核记录时全部 `null`，`blockedReason=REVIEW_RECORDS_REQUIRED`。

## 5. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-label-governance")
print(core.run("operator/dm-label-governance/dataset/sample/result_demo.jsonl", {}, 42,
               "operator/runtime/output/op07-demo")["metrics"])
PY
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-label-governance/tests -q
```

## 6. 已知限制

1. 冲突规则为联调口径（不同一级类目 + 均高于阈值），需业务确认；
2. 最近节点用编辑距离，语义近邻未接入向量；
3. PII 正则存在误报/漏报，只作提示；
4. 审核类指标依赖人工审核记录（H-05），当前为 `null`。

## 7. 版本与证据

`operatorVersion=0.1.0`、`modelVersion=null`、`treeVersion=taxonomy-1013-pending`；
证据目录 `operator/dm-label-governance/output/evidence/<runId>/`。
