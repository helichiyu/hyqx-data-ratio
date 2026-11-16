# OP-03 输入输出数据契约

## 1. 输入

OP-02 运行目录（含 `records.jsonl`）或 `records.jsonl` 文件。只使用以下字段：

| 字段 | 用途 |
| --- | --- |
| `record_id` | 结果行主键 |
| `modal` | 仅处理 `text` |
| `text` | 切窗与向量化；空文本记 `EMPTY_TEXT` |
| `partitions` / `hashes` / `quality` | 不参与聚类，保留在来源记录中 |

## 2. 输出

`result.jsonl`：

```json
{"record_id": "r_…", "cluster": 3, "distance_to_centroid": 0.182345, "chunk_count": 2, "text_chars": 812}
```

`vector_ids.jsonl`：

```json
{"row": 0, "record_id": "r_…"}
```

`vectors.npy`：`(N, 768) float16`，行号与 `vector_ids.jsonl` 一致；已 L2 归一化。
`centroids.npy`：`(K, 768) float32`。
`cluster_summary.json`：

```json
{
  "k": 15,
  "silhouette": 0.060446,
  "search": [{"k": 15, "silhouette": 0.060446}],
  "clusters": [
    {"cluster": 0, "size": 89, "topTerms": ["学习", "模型", "数据"], "representativeRecordIds": ["r_…"], "maxDistance": 0.31}
  ]
}
```

`metrics.json` 字段见 README；`manifest.json` 按 `docs/算子开发/schemas/manifest.schema.json`。

## 3. 失败 reasonCode

`EMPTY_TEXT`、`RECORD_JSON_INVALID`、`RECORD_NOT_OBJECT`、`DEPENDENCY_UNAVAILABLE`（模型缺失，HTTP 503）。

## 4. 样例

`dataset/sample/records_demo.jsonl`：8 条自建文本，可直接运行：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-text-clustering")
print(core.run("operator/dm-text-clustering/dataset/sample/records_demo.jsonl", {"k": 2}, 42,
               "operator/runtime/output/op03-demo")["metrics"])
PY
```
