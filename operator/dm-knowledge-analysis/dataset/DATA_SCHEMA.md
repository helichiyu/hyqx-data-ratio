# OP-13 输入输出数据契约

## 1. 输入

OP-02 运行目录（`records.jsonl`）；只消费 `modal=text`：

| 字段/参数 | 用途 |
| --- | --- |
| `text` | 术语匹配、知识类型、语体（截断 `maxTextChars=50000`） |
| `metadata.capturedAt` / 正文年份 | 热点/长尾分类 |
| `params.glossary_path` | 术语表 jsonl（`{"term","category"}`），须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |
| `params.as_of` | 热点基准日，默认批次最大年份 12-31 |

## 2. 输出

`result.jsonl`：

```json
{
  "record_id": "r_know_demo_001",
  "textChars": 33,
  "terms": {"status": "ok", "hitCount": 3, "matchedTerms": 3, "coverage": 0.75, "densityPer100Chars": 9.09, "topTerms": ["训练数据", "模型", "机器学习"]},
  "knowledgeType": "fact",
  "knowledgeShares": {"fact": 0.667, "reasoning": 0.0, "creative": 0.333},
  "style": "general",
  "styleConfidence": 0.0,
  "year": 2025,
  "freshnessClass": "hot"
}
```

- `terms.status=unavailable` + `GLOSSARY_UNAVAILABLE`：未提供术语表；
- `knowledgeType` ∈ `fact/reasoning/creative/unknown`；
- `freshnessClass` ∈ `hot/long_tail/unknown`（窗口 365 天可配置）；
- 实体覆盖率不产出：`metrics.entityCoverage.status=unavailable` + `KG_UNAVAILABLE`。

辅助产物：`failures.jsonl`、`input_manifest.json`、`manifest.json`、`summary.json`。

## 3. 样例

`dataset/sample/{records_demo.jsonl, glossary_demo.jsonl}`：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-knowledge-analysis")
print(core.run("operator/dm-knowledge-analysis/dataset/sample", {}, 42,
               "operator/runtime/output/op13-demo")["metrics"]["knowledgeTypes"])
PY
```
