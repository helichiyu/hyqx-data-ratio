# OP-20 输入输出数据契约

## 1. 输入

| 参数/路径 | 用途 |
| --- | --- |
| `input_path` / `params.records_path` | OP-02 记录（`record_id/text/modal/source/partitions`） |
| `params.labels_path` | OP-05 结果（`labels[].path/confidence`），可选 |
| `params.vectors_path` | OP-03 运行目录：`vectors.npy`（N×768）+ `vector_ids.jsonl`（`record_id,row`） |

bundle.json 格式：`{"recordsPath": "...", "labelsPath": "...", "vectorsPath": "..."}`。

## 2. 输出

| 文件 | 内容 |
| --- | --- |
| `graph_nodes.jsonl` | `{id,type,name,properties}`；type=record/label/entity |
| `graph_edges.jsonl` | `{source,target,type,weight}`；type=ABOUT/MENTIONS/SUBCLASS_OF/CO_OCCURS |
| `neo4j_import.cypher` | MERGE 节点/关系的导入脚本 |
| `graph_stats.json` | 节点/边/实体计数与 ruleBased |
| `index/vectors.npy`、`centroids.npy`、`assignments.npy`、`meta.json` | IVF 索引文件与版本 |
| `query_results.jsonl` | 每查询精确/近似 topK、recordId、score |
| `metrics.json` / `manifest.json` / `summary.json` / `input_manifest.json` / `failures.jsonl` | 指标、版本四件套、输入指纹、失败 |

`metrics.vector`：

```json
{"indexVersion": "e866dc2c28574af9", "count": 488, "dimension": 768,
 "nlist": 16, "nprobe": 4, "topK": 10, "queryCount": 20,
 "recallAtK": {"1": 1.0, "5": 0.98, "10": 0.95}, "qps": 800.0, "buildSeconds": 0.12}
```

## 3. 样例

`dataset/sample/{records.jsonl, labels.jsonl, vectors/}`：3 条记录、2 条标签、4×768 向量。

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
os.environ.setdefault("OUTPUT_DIR", "operator/runtime/output")
import inference
core = inference._import_operator_core("dm-graph-indexing")
print(core.run("operator/dm-graph-indexing/dataset/sample/records.jsonl",
               {"records_path": "operator/dm-graph-indexing/dataset/sample/records.jsonl",
                "labels_path": "operator/dm-graph-indexing/dataset/sample/labels.jsonl",
                "vectors_path": "operator/dm-graph-indexing/dataset/sample/vectors"},
               42, "operator/runtime/output/op20-demo")["metrics"]["graph"])
PY
```
