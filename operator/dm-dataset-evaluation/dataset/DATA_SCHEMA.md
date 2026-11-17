# OP-18 输入输出数据契约

## 1. 输入

| 参数/路径 | 用途 |
| --- | --- |
| `input_path` | OP-17 运行目录（`manifest.json` 的 `dataset.files` 与 Parquet 分片） |
| `params.ratio` | 抽样比例（默认 0.1，按模态分层） |
| `params.truth_path` | 真值 JSONL：`{"record_id": "...", "path": ["一级","二级","三级"]}` 或 `{"record_id":"...","label":"一级/二级/三级"}` |
| `params.labels_path` | OP-05 运行目录（校验 modelVersion/treeVersion 一致） |
| `params.compliance_terms_path` | 敏感词表（JSON 字符串数组或每行一词） |
| `params.copyright_hashes_path` | 版权哈希库（JSON 数组或每行一个 SHA-256/MD5） |

OP-17 Parquet 需包含：`record_id/label/modal/text/quality_json/hashes_json/confidence`。

## 2. 输出

| 文件 | 内容 |
| --- | --- |
| `sampled.jsonl` | 抽样清单：`record_id/modal/sampleRank/label/confidence` |
| `evaluation.json` | `sampling/truth/proxy/compliance/score/versionCheck` |
| `confusion.json` | 混淆矩阵（有真值时） |
| `wrong_labels.jsonl` | 错标清单（有真值时，最多 1000 条） |
| `compliance.json` | 词表/版权命中与命中率，或 `unavailable` |
| `metrics.json` / `manifest.json` / `summary.json` / `input_manifest.json` / `failures.jsonl` | 指标、版本四件套、汇总、输入指纹、失败 |

`evaluation.json` 关键结构：

```json
{
  "sampling": {"ratioRequested": 0.1, "ratioEffective": 0.1, "perModal": {"text": {...}}},
  "truth": {"status": "unavailable", "blockedReason": "TRUTH_REQUIRED", "accuracy": null,
            "macroF1": null, "confusion": null, "wrongLabels": []},
  "proxy": {"proxy": true, "pathLegalityRate": 1.0, "meanConfidence": 0.42, "meanCompleteness": 1.0},
  "compliance": {"status": "unavailable", "reasonCode": "COMPLIANCE_RESOURCES_REQUIRED"},
  "score": {"score": 0.9, "grade": "excellent", "components": {...}}
}
```

## 3. 样例

`dataset/sample/truth.jsonl` 为真值格式样例；完整可运行链路：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ["INPUT_DIR"] = "operator"
os.environ["OUTPUT_DIR"] = "operator/runtime/output"
import inference
pack = inference._import_operator_core("dm-dataset-packaging")
pack.run("operator/dm-dataset-packaging/dataset/sample/plan",
         {"records_path": "operator/dm-dataset-packaging/dataset/sample/records.jsonl",
          "labels_path": "operator/dm-dataset-packaging/dataset/sample/labels.jsonl"},
         42, "operator/runtime/output/op17-demo")
eval_core = inference._import_operator_core("dm-dataset-evaluation")
print(eval_core.run("operator/runtime/output/op17-demo",
                    {"ratio": 0.5, "truth_path": "operator/dm-dataset-evaluation/dataset/sample/truth.jsonl"},
                    42, "operator/runtime/output/op18-demo")["metrics"]["score"])
PY
```

`truth.jsonl` 中 `s1` 正确、`s2` 故意错标，用于演示准确率与错标清单。
