# OP-21 输入输出数据契约

## 1. 输入

| 参数/路径 | 用途 |
| --- | --- |
| `input_path` | 对象 JSONL：`{record_id, label, level1?, riskLevel?, modal?}`；或 OP-05 `result.jsonl`（取最高置信标签） |
| `params.risk_path` | 风险 JSONL：`{record_id, riskLevel}`（high/critical 必选） |
| `params.expert_path` | 专家标注 JSONL：`{record_id, expertId, label}`，同一记录可多专家 |
| `params.ratio` | 抽样比例，钳制 5%–10% |

## 2. 输出

| 文件 | 内容 |
| --- | --- |
| `sampled.jsonl` | `record_id/label/level1/riskLevel/stratum/selectedBy` |
| `agreement.json` | `status/kappa/alpha/consensus/accuracyVsConsensus/macroF1VsConsensus/perLabel/disputes` |
| `disputes.jsonl` | 争议样本：记录、自动标签、共识、各专家评分、分歧标签 |
| `metrics.json` | `sampling`（population/sampled/ratioEffective/perStratum/highRisk*）与 `agreement` 摘要 |
| `manifest.json` / `summary.json` / `input_manifest.json` / `failures.jsonl` | 版本四件套、输入指纹、失败 |

无专家标注时：

```json
{"status": "blocked", "blockedReason": "EXPERT_ANNOTATIONS_REQUIRED",
 "kappa": null, "alpha": null, "consensus": null, "perLabel": null, "disputes": []}
```

## 3. 样例

`dataset/sample/{objects.jsonl, risk.jsonl, expert.jsonl}`：10 条对象、1 条高风险、2 位专家（1 条争议）。

```bash
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
