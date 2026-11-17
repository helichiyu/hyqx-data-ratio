# OP-10 输入输出数据契约

## 1. 输入

OP-02 运行目录（`records.jsonl`）或记录文件；只消费 `modal=text`：

| 字段 | 用途 |
| --- | --- |
| `record_id` | 结果主键 |
| `text` | 分句/分词/句法/词汇/语体/六维评分（截断 `maxTextChars=50000`） |

可选参数 `domain_labels_path`：OP-06 结果目录/文件（须在 `INPUT_DIR`/`OUTPUT_DIR` 内），
用于 `domainMatch` 子指标；未提供时 domain 组不参与评分。

## 2. 输出

`result.jsonl`：

```json
{
  "record_id": "r_text_demo_001",
  "textChars": 96,
  "sentenceCount": 4,
  "sentenceCharsMean": 24.0,
  "clausesPerSentenceMean": 1.75,
  "clauseDepthMean": 1.5,
  "passiveRate": 0.0,
  "completeSentenceRate": 1.0,
  "punctuationPer100Chars": 8.3,
  "tokenCount": 42,
  "uniqueTokens": 35,
  "ttr": 0.833333,
  "msttr": 0.85,
  "mtld": 26.4,
  "meanTokenChars": 1.76,
  "genre": "academic",
  "genreConfidence": 0.166667,
  "dimensions": {
    "sentenceCompleteness": 10.0,
    "clauseComplexity": 1.875,
    "lexicalRichness": 8.5,
    "informationDensity": 4.375,
    "domainMatch": null,
    "genreFit": 1.666667
  },
  "groups": {"structure": 5.9375, "semantic": 6.85, "domain": null},
  "overall": 6.335,
  "lowFit": false,
  "reasonCode": "DOMAIN_LABELS_UNAVAILABLE"
}
```

空文本记录输出全 `null` 指标并写 `reasonCode=EMPTY_TEXT`。

辅助产物：`low_fit.jsonl`（整体分 < 3.0）、`failures.jsonl`、`input_manifest.json`、
`manifest.json`、`summary.json`；`metrics.json` 含六维与 overall 的 P50/P90/P99、语体分布。

## 3. 样例

`dataset/sample/records_demo.jsonl`：3 条自建中文文本：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-text-profiling")
print(core.run("operator/dm-text-profiling/dataset/sample", {}, 42,
               "operator/runtime/output/op10-demo")["metrics"]["distributions"])
PY
```
