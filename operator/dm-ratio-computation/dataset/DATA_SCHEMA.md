# OP-15 输入输出数据契约

## 1. 输入

| 参数/路径 | 用途 |
| --- | --- |
| `input_path` | OP-02 运行目录（`records.jsonl`，提供 `source` 与文本长度） |
| `params.labels_path` | OP-05 运行目录/结果文件（`labels[].path`），须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |
| `params.target_total` | 目标投喂总量（默认 100000） |
| `params.label_weights` | 标签权重覆盖（`{labelPath: weight}`，默认 1.0） |

## 2. 输出

`result.jsonl`（三列方案表，逐标签）：

```json
{"label": "新闻与资讯/科技新闻/产品发布与行业动态", "level1": "新闻与资讯", "level2": "新闻与资讯/科技新闻",
 "count": 10, "labelWeight": 1.0, "effectiveCount": 10.0, "share": 0.6667, "sharePercent": 66.67, "feedCount": 66667}
```

`validation.json`（校验单）每项结构：

```json
{"id": "sum_100", "actual": 1.0, "threshold": 1.0, "tolerance": 0.001, "passed": true, "source": "任务书 S4 门禁 / baseline ratio.sum_target"}
```

检查项：`sum_100`、`core_label_coverage`、`level1_coverage`、`level2_coverage`、`min_sample`、`inventory_gap`。

`plan.json`：方案表 + 归一化参数 + 库存摘要。`metrics.json` 汇总份额、误差、检查通过数、缺口。
辅助产物：`input_manifest.json`、`manifest.json`、`summary.json`。

## 3. 样例

`dataset/sample/{records_demo.jsonl, labels_demo.jsonl}`：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys, os; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
import inference
core = inference._import_operator_core("dm-ratio-computation")
print(core.run("operator/dm-ratio-computation/dataset/sample",
               {"labels_path": "operator/dm-ratio-computation/dataset/sample/labels_demo.jsonl", "target_total": 10}, 42,
               "operator/runtime/output/op15-demo")["metrics"]["checks"])
PY
```
