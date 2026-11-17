# OP-17 输入输出数据契约

## 1. 输入

| 参数/路径 | 用途 |
| --- | --- |
| `input_path` | OP-15 运行目录（`plan.json`：`rows[].label/level1/level2/feedCount/bySource`） |
| `params.records_path` | OP-02 运行目录/`records.jsonl`（`record_id/modal/source/text/metadata/quality/partitions/hashes`） |
| `params.labels_path` | OP-05 运行目录/`result.jsonl`（`record_id/labels[].path/confidence/modelVersion/treeVersion`） |
| `params.resume` | 是否复用 checkpoint（默认 true） |

路径必须在 `INPUT_DIR`/`OUTPUT_DIR` 内；未传时回退 OP-15 `input_manifest.json` 的 `recordsPath`/`labelsPath`。

## 2. 输出

| 文件 | 内容 |
| --- | --- |
| `selected.jsonl` | 逐条选样：`record_id/label/level1/level2/confidence/selectionRank` |
| `quota.json` | 逐标签 `quota/available/selected/gap/rate/status/recordIds` |
| `bias.json` | 逐标签偏差、来源分布偏差、加权平均偏差、warn |
| `dataset/**/part-*.parquet` | 成品分片（zstd，`modal/source/dt` 分区） |
| `manifest.json` | 运行版本、seed、dataset 文件 rows/bytes/MD5/SHA-256、配额汇总 |
| `checkpoint.json` | 续跑状态（completedLabels/perLabel/selectedIds，含 paramsHash/seed） |
| `metrics.json` / `summary.json` / `input_manifest.json` / `failures.jsonl` | 指标、汇总、输入指纹、失败与跳过清单 |

Parquet 列：

```json
{"record_id": "r_...", "label": "新闻与资讯/科技新闻/产品发布与行业动态",
 "level1": "新闻与资讯", "level2": "新闻与资讯/科技新闻", "confidence": 0.83,
 "selection_rank": 0, "modal": "text", "source": "web_text", "dt": "2026-11-16",
 "text": "...", "metadata_json": "{...}", "quality_json": "{...}",
 "partitions_json": "{...}", "hashes_json": "{...}"}
```

## 3. 样例

`dataset/sample/{plan/plan.json, records.jsonl, labels.jsonl}`：2 标签、3 条记录。

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator/dm-dataset-packaging/dataset/sample")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-dataset-packaging")
print(core.run("operator/dm-dataset-packaging/dataset/sample/plan",
               {"records_path": "operator/dm-dataset-packaging/dataset/sample/records.jsonl",
                "labels_path": "operator/dm-dataset-packaging/dataset/sample/labels.jsonl"},
               42, "operator/runtime/output/op17-demo")["metrics"])
PY
```
