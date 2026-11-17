# OP-21 专家校验（`dm-expert-validation`）

- 语义编码：`tool_expert_validation_v1`
- 阶段/优先级：S6 / P1
- 版本：`0.1.1`
- 模型：无

## 1. 用途与边界

**做**：对待校验对象做 5%–10% 分层抽样（固定 seed、高风险必选），输出抽样清单与实抽比例；
消费专家标注计算 Cohen's Kappa、Krippendorff's Alpha、共识、逐标签 P/R/F1、争议 TopN。

**不做**：不做任务派发/签署/工单状态机；不生成专家标注；无标注时不编造一致性指标。

## 2. 抽样口径

```text
分层字段 = params.stratumField（默认 level1）
每层按 sha256(seed|record_id) 升序
每层抽样数 = max(minPerStratum, ceil(层记录数 × ratio))，ratio 钳制在 5%–10%
高风险（high/critical）未入样的记录强制补入，selectedBy=high_risk
```

- 小样本层会因 `minPerStratum` 导致实抽比例高于 10%，`metrics.sampling.ratioEffective` 如实记录；
- 高风险来源：`params.risk_path`（JSONL `{record_id, riskLevel}`）或对象自带 `riskLevel`；
- 固定 seed 重跑抽样清单一致。

## 3. 一致性口径

| 指标 | 定义 |
| --- | --- |
| Cohen's Kappa | 专家两两共同标注项的 Kappa 均值；`Pe=1` 时记 null |
| Krippendorff's Alpha | 名义 alpha；只用 ≥2 位专家评分的样本 |
| 共识 | 多数票；平票记 `DISPUTED` |
| 准确率/宏 F1 | 以共识为金标准，对比自动标签（DISPUTED 不计） |
| 争议 | 专家标签不一致的样本，按分歧标签数/评分数排序 |

- 无专家标注（H-05）时 `agreement.status=blocked`、`blockedReason=EXPERT_ANNOTATIONS_REQUIRED`，
  抽样清单仍产出；
- 阈值 `kappaGood=0.6`、`alphaGood=0.667` 为联调初值（H-03）。

## 4. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `input_path` | 必填 | 对象 JSONL（`record_id/label/level1/riskLevel`）或 OP-05 结果目录 |
| `params.risk_path` | 无 | 风险等级 JSONL（OP-22 或平台提供） |
| `params.expert_path` | 无 | 专家标注 JSONL：`{record_id, expertId, label}` |
| `params.ratio` | 0.1 | 抽样比例（钳制 5%–10%） |

## 5. 运行与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-expert-validation/tests
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-expert-validation")
print(core.run("operator/dm-expert-validation/dataset/sample/objects.jsonl",
               {"risk_path": "operator/dm-expert-validation/dataset/sample/risk.jsonl",
                "expert_path": "operator/dm-expert-validation/dataset/sample/expert.jsonl"},
               42, "operator/runtime/output/op21-demo")["metrics"]["agreement"])
PY
```

## 6. 已知限制

1. 专家标注、共识规则由人工提供/确认（H-05）；无标注时一致性 blocked；
2. 高风险定义来自平台风险结果（OP-22 或风险清单），算子不自行判定；
3. 总样本量先按 5%–10% 确定，再按层规模分配、每层至少 1 条；分层数超过目标样本量时实抽比例会高于 10%，如实记录；
4. 任务派发/签署/统计看板归平台。

## 7. 版本与证据

`operatorVersion=0.1.1`、`modelVersion=null`、`paramsHash`/`seed` 入 manifest/metrics；
证据目录 `operator/dm-expert-validation/output/evidence/<runId>/`。
