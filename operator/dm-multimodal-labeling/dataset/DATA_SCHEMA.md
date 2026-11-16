# OP-05 输入输出数据契约

## 1. 输入

OP-02 运行目录（推荐）或 `records.jsonl`：

| 字段 | 用途 |
| --- | --- |
| `record_id` / `modal` | 主键与模态路由 |
| `text` | 文本证据 |
| `metadata.extra.derivedFrom` | 视频与拆流音轨的关联 |
| `index/metadata.parquet.standard_path` | 媒体标准产物路径（缺失时按约定路径回退） |

媒体：`standard/images/<rid>.webp`、`standard/audio/<rid>.wav`、`standard/video/<rid>.mp4`。

## 2. 输出

`result.jsonl`：

```json
{
  "record_id": "r_…",
  "modal": "video",
  "labels": [{
    "path": ["语音与人声", "人声属性", "年龄与性别属性"],
    "confidence": 0.376989,
    "topK": [
      {"path": ["语音与人声", "人声属性", "年龄与性别属性"], "confidence": 0.376989, "similarity": 0.551},
      {"path": ["…"], "confidence": 0.24, "similarity": 0.543}
    ],
    "evidence": {"source": "video_fusion", "ocr": {...}, "asr": {...}},
    "modelVersion": "bge-base-zh-v1.5",
    "treeVersion": "taxonomy-1013-pending"
  }],
  "unclassified": false,
  "reasonCode": null,
  "top1": 0.376989,
  "margin": 0.008,
  "evidence": {"source": "video_fusion", "chars": 755}
}
```

未归类样本 `labels=[]`，`reasonCode` ∈：

| reasonCode | 含义 |
| --- | --- |
| `UNCLASSIFIED_EMPTY_TEXT` | 文本为空 |
| `UNCLASSIFIED_NO_TEXT_EVIDENCE` | 图像/视频无 OCR 文字 |
| `UNCLASSIFIED_NO_SPEECH` | 音频无语音 |
| `UNCLASSIFIED_LOW_SIMILARITY` | top1 余弦 <0.45 |
| `UNCLASSIFIED_LOW_CONFIDENCE` | topK softmax <0.25 |
| `UNCLASSIFIED_SMALL_MARGIN` | top1-top2 <0.005 |
| `STANDARD_MEDIA_MISSING` | 标准媒体缺失 |
| `OCR_FAILED` / `ASR_FAILED` / `KEYFRAME_FAILED` | 工具失败 |
| `DEPENDENCY_UNAVAILABLE` | 模型/权重不可用 |

`label_vectors.npy`：`(279, 768) float16`，与 `label_ids.jsonl` 行号对应，标签来自
`operator/baseline/tree-snapshot.json` 内容树叶子（`treeVersion=taxonomy-1013-pending`）。

## 3. 样例

`dataset/sample/records_demo.jsonl`：2 条自建文本，可直接运行：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-multimodal-labeling")
print(core.run("operator/dm-multimodal-labeling/dataset/sample/records_demo.jsonl", {}, 42,
               "operator/runtime/output/op05-demo")["metrics"])
PY
```
