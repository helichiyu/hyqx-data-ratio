# OP-08 输入输出数据契约

## 1. 输入

OP-02 运行目录（`records.jsonl`）或记录文件：

| 字段 | 用途 |
| --- | --- |
| `record_id` / `modal` / `source` | 主键、模态计数、六类来源分布 |
| `text` | 字符数/字节数（UTF-8） |
| `metadata.durationSec` / `frameCount` / `sizeBytes` / `capturedAt` | 时长、帧数、存储、时间 |
| `quality.completeness` / `decodable` | AHP 的 evaluation 维度、完整率参考 |
| `partitions.dt` | 分位数/新鲜度的时间基准 |

可选参数 `domain_labels_path`：OP-06 运行目录或 `result.jsonl`（须位于 `INPUT_DIR`/`OUTPUT_DIR` 内）；
可选 `as_of`（`YYYY-MM-DD`）覆盖新鲜度基准日，默认取批次最大 `dt`。

## 2. 输出

`result.jsonl`（逐记录）：

```json
{
  "record_id": "r_…",
  "modal": "text",
  "source": "web_text",
  "textChars": 96,
  "textBytes": 288,
  "durationSec": null,
  "frameCount": null,
  "sizeBytes": 96,
  "standardBytes": null,
  "dt": "2025-03-02",
  "completeness": 1.0
}
```

`metrics.json` 关键字段：

| 字段 | 含义 |
| --- | --- |
| `scale.recordCount` / `modalCounts` | 条数与模态分布 |
| `scale.textChars` / `textBytes` / `durationSec` / `frameCount` / `sizeBytes` / `standardBytes` | 规模汇总 |
| `scale.standardCompressionRatio` | 标准产物字节 / 原始字节（有标准产物时） |
| `scale.percentiles.{textChars,durationSec,frameCount,sizeBytes}` | nearest-rank P50/P90/P99 |
| `sourceDistribution.classes.*.sharePercent` | 六类来源占比（合计 100） |
| `sourceDistribution.ahp` | 维度权重、λmax、CI、CR、是否一致（CR<0.1） |
| `sourceDistribution.corpusCredibility` | 语料总分 = Σ 类占比 × 类总分 |
| `domainCoverage.status` | `ok` 或 `unavailable` + `reasonCode` |
| `domainCoverage.coverage.{level1,level2,leaf,labeledRecordRate}` | 四种覆盖率口径 |

辅助产物：`source_distribution.json`、`domain_coverage.json`、`failures.jsonl`、
`input_manifest.json`、`manifest.json`、`summary.json`。

## 3. 样例

`dataset/sample/records_demo.jsonl`：4 条自建记录（文本/图像/音频/视频）：

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-corpus-profiling")
print(core.run("operator/dm-corpus-profiling/dataset/sample", {}, 42,
               "operator/runtime/output/op08-demo")["metrics"]["scale"])
PY
```
