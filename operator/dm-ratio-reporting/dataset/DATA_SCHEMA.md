# OP-19 输入输出数据契约

## 1. 输入

`input_path` 为 `bundle.json`：

```json
{
  "operator_results": {
    "OP-08": "operator/dm-corpus-profiling/output/evidence/<runId>",
    "OP-09": "operator/dm-language-profiling/output/evidence/<runId>",
    "OP-10": "operator/dm-text-profiling/output/evidence/<runId>",
    "OP-14": "operator/dm-quality-analysis/output/evidence/<runId>",
    "OP-05": "operator/dm-multimodal-labeling/output/evidence/<runId>",
    "OP-07": "operator/dm-label-governance/output/evidence/<runId>",
    "OP-15": "operator/dm-ratio-computation/output/evidence/<runId>",
    "OP-17": "operator/dm-dataset-packaging/output/evidence/<runId>",
    "OP-18": "operator/dm-dataset-evaluation/output/evidence/<runId>"
  }
}
```

也可通过 `params.operator_results` 直接传入（优先于 bundle）。每个路径可以是运行目录或
`metrics.json` 文件；路径须在 `INPUT_DIR`/`OUTPUT_DIR` 内。键支持 `OP-08` 或算子目录名
（如 `dm-corpus-profiling`）。

## 2. 输出

| 文件 | 内容 |
| --- | --- |
| `report_package.json` | `dimensions/overall/statusMatrix/conclusions/operatorVersions/evidence/render` |
| `status_matrix.json` | `rows`（key/nameZh/operator/score/grade/weight/status/reason）与 overall |
| `conclusions.jsonl` | `{key, severity, text}` |
| `report.html` | 可选渲染 |
| `metrics.json` | `overallScore/overallGrade/dimensionsAvailable/missing/operatorVersions/render` |
| `manifest.json` / `summary.json` / `input_manifest.json` | 版本四件套、输入指纹、加载/缺失算子 |

维度明细：

```json
{"key": "ratio_compliance", "nameZh": "配比合规", "operator": "OP-15",
 "metric": "checksPassed / checksTotal", "weight": 0.14,
 "score": 0.8333333333, "grade": "good", "status": "ok", "reason": null,
 "raw": {"checksPassed": 5, "checksTotal": 6, "failedChecks": ["inventory_gap"]},
 "thresholds": {"excellent": 1.0, "good": 0.83, "pass": 0.67}}
```

## 3. 样例

`dataset/sample/bundle.json` + 9 个算子的最小 `metrics.json` 样例：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-ratio-reporting")
print(core.run("operator/dm-ratio-reporting/dataset/sample/bundle.json", {}, 42,
               "operator/runtime/output/op19-demo")["metrics"]["overallScore"])
PY
```
