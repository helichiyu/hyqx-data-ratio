# OP-02 输入输出数据契约

## 1. 输入

优先接受 OP-01 的运行目录：

```text
<op01_run_dir>/
├── result.jsonl        # 标准记录（必需）
├── manifest.json       # 上游版本/计数（可选，用于登记与对账）
└── …                   # 媒体源文件（按记录 sourcePath 定位）
```

也接受单独的 `result.jsonl` 文件。**不接受**没有任何记录文件的目录（返回 `RECORDS_NOT_FOUND`）。

记录字段以 `docs/算子开发/schemas/record.schema.json` 为准；OP-02 额外使用：

| 字段 | 用途 |
| --- | --- |
| `metadata.extra.sourcePath` | 原始文件绝对路径（首选） |
| `metadata.extra.file` | 相对路径（回退，与 `source_root` 或记录根组合） |
| `metadata.extra.derivedFrom` | 视频拆流音轨关联的视频记录 ID |
| `hashes.simhash` / `hashes.phash` | 去重；文本归一化后 SimHash 会重算 |
| `partitions.dt` | Parquet 分区键 |

## 2. 标准产物

| 模态 | 容器 | 说明 |
| --- | --- | --- |
| 文本（含 PDF 文本） | Parquet（zstd） | 按 `modal/source/dt` 分区；列见 `utils/writer.py:PARQUET_SCHEMA` |
| 图像 | WebP | quality 90；保留宽高/哈希/pHash 于索引 |
| 音频 | WAV | 16 kHz、mono、pcm_s16le |
| 视频 | MP4（H.264/AAC） | 无 libx264 时流复制；失败时原容器 + 异常标记 |

Parquet 列：

```text
record_id, modal, source, dt, text, text_chars, text_sha256, format, size_bytes,
md5, sha256, simhash, phash, standard_path, duplicate_of, quality_json, metadata_json
```

## 3. 索引（`index/`）

`metadata.parquet` 列：

```text
record_id, modal, source, dt, format, size_bytes, md5, sha256, simhash, phash,
text_chars, empty_text, decodable, completeness, standard_path, duplicate_of, file
```

`missing_fields.json`：必填 metadata/quality/hashes 字段的缺失计数。
`partition_stats.json`：每个分区的记录数与原文字节数。

## 4. 重复与异常

`duplicates.jsonl`：

```json
{
  "groupId": "dup_9cea1e8d8c26",
  "kind": "exact",
  "representative": "r_b93e…",
  "members": ["r_b93e…", "r_bcd6…"],
  "count": 2,
  "modalities": ["text"],
  "evidence": {"sha256": "…"}
}
```

`kind`：`exact` / `near_text` / `near_image`。`anomalies.jsonl`：

```json
{"recordId": "r_…", "type": "SILENT_AUDIO", "detail": "静音占比 1.0"}
```

类型：`EMPTY_TEXT`、`DECODE_ERROR`、`SCANNED_PAGES_NO_OCR`、`SILENT_AUDIO`、`BLACK_FRAME`、`STANDARDIZATION_FALLBACK`。

## 5. 跨模态关联（`associations.jsonl`）

```json
{"level": "file", "key": "file:batch.zip/v.mp4", "count": 2,
 "modalities": ["audio", "video"], "recordIds": ["r_…", "r_…"], "hasDerivedStream": true}
{"level": "archive", "key": "archive:batch.zip", "count": 4,
 "modalities": ["audio", "image", "text", "video"], "modalCounts": {"audio": 1, "image": 1, "text": 1, "video": 1},
 "sampleRecordIds": ["r_…"]}
```

## 6. 失败 reasonCode

`RECORDS_NOT_FOUND`、`INPUT_INVALID`、`RECORD_JSON_INVALID`、`RECORD_SCHEMA_INVALID`、`SOURCE_FILE_MISSING`、`STANDARDIZATION_FAILED`。

## 7. 样例

`dataset/sample/records_demo.jsonl` 为自建最小记录，可直接运行；完整链路样例见
`docs/算子开发/samples/`（授权状态见 `SOURCES.md`）。
