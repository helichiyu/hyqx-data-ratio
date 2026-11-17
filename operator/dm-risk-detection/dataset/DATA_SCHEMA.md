# OP-22 输入输出数据契约

## 1. 输入

`input_path` 为 `bundle.json`：

```json
{"operator_results": {
  "OP-08": "path/to/run", "OP-09": "path/to/run", "OP-10": "path/to/run",
  "OP-14": "path/to/run", "OP-15": "path/to/run", "OP-17": "path/to/run",
  "OP-18": "path/to/run", "OP-19": "path/to/run"
}}
```

也可用 `params.operator_results`。每个路径可为运行目录或 `metrics.json`；
路径须在 `INPUT_DIR`/`OUTPUT_DIR` 内。

## 2. 输出

`risks.jsonl`：

```json
{"id": "R-01-OP-09", "ruleId": "R-01", "type": "时效过时", "level": "critical",
 "severity": 3, "operator": "OP-09", "metric": "time.freshnessMean", "value": 0.14,
 "threshold": {"op": "lt", "warn": 0.4, "critical": 0.2, "triggered": {"op": "lt", "value": 0.2}},
 "minSample": 0, "sampleSize": null, "scope": "corpus",
 "suggestion": "补充近 1–3 年语料...",
 "evidence": {"operator": "OP-09", "metric": "time.freshnessMean", "value": 0.14,
              "metricsPath": ".../metrics.json"},
 "evidenceList": [...], "ruleIds": ["R-01"]}
```

`risk_report.json` 关键字段：

| 字段 | 含义 |
| --- | --- |
| `risks` | 去重/抑制后的风险条目 |
| `evaluatedRules` / `rawHits` / `dedupedCount` | 规则评估与去重计数 |
| `suppressed` / `suppressedCount` | 抑制条目与计数 |
| `noData` | 上游指标缺失的规则 |
| `insufficientSample` | 样本量不足未执行的规则 |
| `outdated` | 过时知识检测状态（`unavailable` + reasonCode） |

## 3. 样例

`dataset/sample/bundle.json` + 5 个算子 metrics（覆盖 critical/warning/info 与无数据场景）。

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-risk-detection")
print(core.run("operator/dm-risk-detection/dataset/sample/bundle.json", {}, 42,
               "operator/runtime/output/op22-demo")["metrics"])
PY
```
