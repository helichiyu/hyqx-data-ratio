# OP-09 输入输出数据契约

## 1. 输入

OP-02 运行目录（`records.jsonl`）或记录文件：

| 字段 | 用途 |
| --- | --- |
| `text` | 语种识别（前 `maxTextChars=20000` 字符）、正文年份抽取 |
| `metadata.capturedAt` | 内容时间（优先） |
| `metadata.region` / `country` / `timezone` | 地域统计（可选，缺失则 `unavailable`） |
| `partitions.dt` | 仅记录接入日期，不作为内容时间参与新鲜度 |

可选参数 `as_of`（`YYYY-MM-DD`）覆盖新鲜度基准日，默认取批次最大内容年份的 12-31。

## 2. 输出

`result.jsonl`：

```json
{
  "record_id": "r_lang_zh_001",
  "modal": "text",
  "language": "zh",
  "confidence": 0.98,
  "status": "identified",
  "reasonCode": null,
  "timeSource": "capturedAt",
  "year": 2025,
  "quarter": 2,
  "freshness": 0.6,
  "hasRegion": false
}
```

- `status` ∈ `identified` / `mixed` / `unknown`；
- `language` ∈ `zh/en/ja/ko/ru/ar/de/fr/es/unknown`（规则识别，非模型输出）；
- `timeSource` ∈ `capturedAt` / `text_iso_date` / `text_year` / `unknown`；
- `freshness`：近 1 年 0.6、近 3 年 0.3、3 年以上 0.1、无时间 `null`；
- `reasonCode` ∈ `EMPTY_TEXT` / `NO_LETTERS` / `LOW_SCRIPT_COVERAGE` / `LOW_CONFIDENCE_MIXED` / `LOW_CONFIDENCE_UNKNOWN`。

`metrics.json` 关键字段：`language.counts/shares/statusCounts/confidenceMean`、
`time.yearCounts/quarterCounts/timeSourceCounts/freshnessMean/staleShare/knownTimeRatio`、
`region.status`。

辅助产物：`region_distribution.json`、`failures.jsonl`、`input_manifest.json`、`manifest.json`、`summary.json`。

## 3. 样例

`dataset/sample/records_demo.jsonl`：中文/英文/日文/空文本各一条：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-language-profiling")
print(core.run("operator/dm-language-profiling/dataset/sample", {}, 42,
               "operator/runtime/output/op09-demo")["metrics"]["language"])
PY
```
