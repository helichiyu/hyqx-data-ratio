# OP-16 输入输出数据契约

## 1. 输入

| 参数/路径 | 用途 |
| --- | --- |
| `input_path` | OP-15 运行目录（含 `plan.json`；需 OP-15 ≥0.1.1 的 `bySource`）或 `plan.json`/`result.jsonl` 文件 |
| `params.plan_path` | 覆盖方案表路径（须在 `INPUT_DIR`/`OUTPUT_DIR` 内） |
| `params.target_total` | 目标投喂总量，默认取方案表 `normalization.targetTotal` |
| `params.orientation` | `balanced`（默认）/ `general` / `professional` |
| `params.target_capability` | 六维目标能力 `{language,knowledge,reasoning,expertise,coding,dialogue}`，自动归一化 |

方案表行（OP-15 输出）关键字段：

| 字段 | 用途 |
| --- | --- |
| `label` / `level1` / `level2` | 标签与内容树 rollup |
| `share` | 当前配比占比（合计必须为 1） |
| `count` | 真实库存条数（补数缺口） |
| `bySource.{source}.effectiveCount` | 来源→能力映射；缺失时返回 `PLAN_SOURCE_BREAKDOWN_MISSING`，不推算 |

## 2. 输出

`result.jsonl`（逐标签建议）：

```json
{"label": "新闻与资讯/科技新闻/产品发布与行业动态", "level1": "新闻与资讯",
 "currentShare": 0.5, "recommendedShare": 0.6, "delta": 0.1,
 "inventory": 50, "currentFeedCount": 50, "recommendedFeedCount": 60, "gap": 10,
 "recommendedSources": [{"source": "web_text", "alignment": 0.23, "shareOfGap": 1.0}],
 "capabilityContribution": {"language": 0.15, "knowledge": 0.125, "...": 0.0}}
```

| 文件 | 内容 |
| --- | --- |
| `capability.json` | 六维能力分/score10、逐标签贡献、达成度、领域占比、偏见、映射版本 |
| `recommendation.json` | 目标能力、优化过程、约束单、达成度对比、增减 Top10 |
| `topup.json` | 全部标签缺口、TopN、推荐补数来源、来源补样量、补齐后能力预测、未覆盖领域清单 |
| `benchmark.json` | 当前/均衡/通用/专业（/custom）对标矩阵与目标模板 |
| `metrics.json` | 汇总指标（能力、达成度、约束、偏见、补数、对标、版本） |
| `input_manifest.json` / `manifest.json` / `summary.json` | 输入指纹、版本四件套、产物哈希 |

阻断输入（方案表为空、占比≠1、缺来源拆分）返回 `metrics.blockedReason` 与空 `result.jsonl`，
不输出能力分/建议，不伪造结果。

## 3. 样例

`dataset/sample/plan/plan.json`：3 个标签（网络文本/代码/对话各 1），目标总量 100。

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
import inference
core = inference._import_operator_core("dm-ratio-analysis")
print(core.run("operator/dm-ratio-analysis/dataset/sample/plan", {}, 42,
               "operator/runtime/output/op16-demo")["metrics"]["recommendation"])
PY
```
