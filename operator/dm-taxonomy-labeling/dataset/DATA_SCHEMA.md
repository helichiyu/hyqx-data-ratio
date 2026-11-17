# OP-06 输入输出数据契约

## 1. 输入

OP-02 运行目录（含 `records.jsonl`）或记录文件 `.jsonl`；只消费 `modal=text`：

| 字段 | 用途 |
| --- | --- |
| `record_id` | 结果主键 |
| `modal` | 非 `text` 记录跳过并计数（`skippedNonText`） |
| `text` | 向量化内容（截断到 `limits.maxTextChars=20000`） |

领域树/能力树来自 `operator/baseline/tree-snapshot.json` 的 `domain`、`ability` 空间，
`treeVersion=taxonomy-1013-pending`（H-02 待确认）。

## 2. 输出

`result.jsonl`（逐条一行）：

```json
{
  "record_id": "r_…",
  "domainLabels": [{
    "path": ["信息技术", "语言智能", "机器翻译"],
    "confidence": 0.539224,
    "similarity": 0.447047,
    "topK": [{"path": ["…"], "confidence": 0.539224, "similarity": 0.447047}],
    "evidence": {"source": "text", "chars": 55, "preview": "Proprietary software…"},
    "modelVersion": "bge-base-zh-v1.5",
    "treeVersion": "taxonomy-1013-pending"
  }],
  "abilityLabels": [{"path": ["…"], "confidence": 0.263311, "similarity": 0.477585, "topK": [], "evidence": {}, "modelVersion": "…", "treeVersion": "…"}],
  "domainUnknown": false,
  "abilityUnknown": true,
  "topK": {"domain": [{"path": ["…"], "confidence": 0.539224, "similarity": 0.447047}], "ability": []},
  "unclassified": false,
  "reasonCode": null,
  "evidence": {"source": "text", "chars": 55, "preview": "…"}
}
```

- 两个空间**严格分离**：`domainLabels` 只取自领域树（209 叶子），`abilityLabels` 只取自能力树（65 叶子）；每空间最多 `maxLabels=3` 条。
- `domainUnknown` / `abilityUnknown=true`：该空间无标签达到阈值，语义为「未明确」，不外推到其它空间。
- `unclassified=true`：两个空间均无标签；`reasonCode` ∈：

| reasonCode | 含义 |
| --- | --- |
| `UNCLASSIFIED_EMPTY_TEXT` | 文本为空或仅空白 |
| `UNCLASSIFIED_LOW_SIMILARITY` | 所有路径余弦相似度低于阈值 |
| `RECORD_JSON_INVALID` | 输入行不是合法 JSON 对象 |

辅助产物：

```text
label_vectors_{domain,ability}.npy  # (N,768) float16，与 label_ids_*.jsonl 行号对应
label_ids_{domain,ability}.jsonl    # {row, path, name}
metrics.json / manifest.json / failures.jsonl / input_manifest.json / summary.json
```

## 3. 样例

`dataset/sample/records_demo.jsonl`：2 条自建文本，可直接运行：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-taxonomy-labeling")
print(core.run("operator/dm-taxonomy-labeling/dataset/sample/records_demo.jsonl", {}, 42,
               "operator/runtime/output/op06-demo")["metrics"])
PY
```
