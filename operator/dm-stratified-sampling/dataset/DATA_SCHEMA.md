# OP-04 输入输出数据契约

## 1. 输入

OP-02 运行目录（`records.jsonl`）或记录文件；可选上游映射：

| 参数 | 用途 |
| --- | --- |
| `cluster_path` | OP-03 结果目录/文件（`record_id` → `cluster`），须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |
| `quality_path` | OP-14 结果目录/文件（`record_id` → `difficultyLevel`），同上 |
| `share` | 覆盖默认抽样比例（默认：大样本 5%，小样本 20%） |

分层键：`source|cluster|quality`，缺失维度为 `MISSING`。

## 2. 输出

`result.jsonl`（样本清单）：

```json
{"record_id": "r_sample_002", "stratum": "web_text|MISSING|MISSING", "hash": "9f…"}
```

`quota_table.json`：

```json
{
  "target": 2,
  "strata": [
    {"stratum": "web_text|MISSING|MISSING", "population": 2, "quota": 1, "sampled": 1,
     "populationShare": 0.5, "sampleShare": 0.5, "bias": 0.0, "cv": 0.2, "ideal": 1.0, "unmet": false}
  ]
}
```

`metrics.json` 关键字段：`population/target/sampled/shareUsed/allocationBasis/targetMet/
unmetQuota/minTotalMet/stratumCount/duplicateFree/actualRatio/maxAbsBias/unmetStrata/
skippedDimensions`。

## 3. 样例

`dataset/sample/records_demo.jsonl`（4 条、2 类来源）：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-stratified-sampling")
print(core.run("operator/dm-stratified-sampling/dataset/sample", {"share": 0.5}, 42,
               "operator/runtime/output/op04-demo")["metrics"])
PY
```
