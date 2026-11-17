# OP-14 输入输出数据契约

## 1. 输入

OP-02 运行目录（`records.jsonl`）或记录文件；可选参数 `labels_path` 指向 OP-05 运行目录/结果文件
（须在 `INPUT_DIR`/`OUTPUT_DIR` 内；缺失时基尼/覆盖/一致性标 `unavailable`）。

| 字段 | 用途 |
| --- | --- |
| 必填字段（见 `configs/quality.json completeness`） | 完整率 |
| `text` | SimHash 冲突、难度、极性 |
| `metadata.extra.derivedFrom` | 多模态一致性配对 |
| OP-05 `result.jsonl` 的 `labels[].path` | 基尼、标注覆盖、多模态一致性 |

## 2. 输出

`result.jsonl`：

```json
{
  "record_id": "r_quality_demo_001",
  "modal": "text",
  "completeness": 1.0,
  "lowCompleteness": false,
  "missingFields": [],
  "blankText": false,
  "labels": 0,
  "polarity": "neutral",
  "polarityScore": 0.0,
  "difficulty": 42.5,
  "difficultyLevel": "中等"
}
```

`metrics.json` 关键字段：

| 字段 | 含义 |
| --- | --- |
| `completeness.mean` / `lowCompletenessCount` / `missingFieldCounts` | 完整率 |
| `conflict.nearDuplicateGroups` / `conflictGroups` / `conflictRate` | 近重复与冲突 |
| `gini.gini` / `exceedsThreshold` | 标签分布基尼（阈值 0.6） |
| `annotation.coverage` | 标注覆盖率 |
| `multimodalConsistency.consistency` | 跨模态一级标签一致率 |
| `difficulty.counts` | 四档难度计数 |
| `polarity.counts` / `shares` / `balance` | 正/负/中性占比与平衡度 |

辅助产物：`low_quality.jsonl`、`failures.jsonl`、`input_manifest.json`、`manifest.json`、`summary.json`。

## 3. 样例

`dataset/sample/records_demo.jsonl`：3 条自建文本（含一对近重复与一条空文本）：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-quality-analysis")
print(core.run("operator/dm-quality-analysis/dataset/sample", {}, 42,
               "operator/runtime/output/op14-demo")["metrics"]["conflict"])
PY
```
