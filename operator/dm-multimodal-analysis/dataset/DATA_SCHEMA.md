# OP-01 输入输出数据契约

## 1. 输入

`core.run(input_path, params, seed, output_dir)` 的 `input_path` 支持：

| 形式 | 说明 |
| --- | --- |
| 单个文件 | 后缀在四模态白名单内（文本/PDF/图像/音频/视频/zip）；未知后缀记 `MODAL_UNKNOWN` |
| 目录 | 递归扫描；符号链接跳过；`.zip` 防御性展开（只取 basename、白名单、限制成员数/解压总量） |
| `.zip` | HTTP 层先解压；直接调用 `core` 时也会安全展开 |

收件后缀（与 `configs/formats.json` 一致）：

```text
文本   .txt .jsonl .json .xml .md .csv .tsv
文档   .pdf
图像   .jpg .jpeg .png .bmp .webp .tif .tiff .gif
音频   .wav .mp3 .flac .m4a .aac .ogg .opus .aiff
视频   .mp4 .mov .mkv .avi .webm .flv
归档   .zip
```

## 2. 输出记录（`result.jsonl`）

一行一条 JSON，字段以 `docs/算子开发/schemas/record.schema.json` 为准：

```json
{
  "record_id": "r_20357f902445aaefee2f597f",
  "modal": "image",
  "source": "web_text",
  "text": null,
  "metadata": {
    "format": "JPEG",
    "mime": "image/jpeg",
    "sizeBytes": 246616,
    "sha256": "…",
    "md5": "…",
    "width": 1280,
    "height": 1811,
    "capturedAt": null,
    "originalSource": "530384988814704640.jpg",
    "synthetic": false,
    "extra": {
      "file": "530384988814704640.jpg",
      "sourcePath": "E:/…/530384988814704640.jpg",
      "mode": "RGB",
      "dpi": [72.0, 72.0],
      "hasIcc": true,
      "exif": {},
      "detection": {"modal": "image", "confidence": 0.99, "evidence": [...]},
      "sourceEvidence": [...],
      "sourceScores": {"web_text": 0.5, "books": 0.0, "...": 0.0},
      "dtSource": "file_time"
    }
  },
  "quality": {
    "decodable": true,
    "completeness": 1.0,
    "emptyText": false,
    "mojibakeRate": 0.0,
    "decodeError": null,
    "notes": []
  },
  "partitions": {"modal": "image", "source": "web_text", "dt": "2026-11-16"},
  "hashes": {"md5": "…", "sha256": "…", "simhash": null, "phash": "9f2c…"}
}
```

补充约定：

- 文本 jsonl **逐行**一条；记录 ID 由 `相对路径 + 行号 + 文本` 生成，同内容同 ID；
- 文件型记录 ID 由 `相对路径 + 文件 SHA-256` 生成；
- PDF 的页统计放在 `metadata.extra.pdf`：`pageCount/scannedPages/emptyPages/blockPages/fontSizes/ocrStatus`；
- 视频关键帧放在 `metadata.extra.keyframes[] = {index, tsSec, path}`，`path` 相对 `output_dir`；
- 视频音轨拆成独立 `audio` 记录，`metadata.extra.derivedFrom` 指向视频记录 ID；
- `source` 为六类来源规则初判（`operator/baseline/source-map.json`），最终口径由 OP-08 复算；
- `dt` 默认取文件修改时间，可用 `params.dt_source` 覆盖。

## 3. 失败清单（`failures.jsonl`）

```json
{"id": "broken.jpg", "reasonCode": "DECODE_FAILED", "detail": "UnidentifiedImageError: ..."}
```

常见 `reasonCode`：`MODAL_UNKNOWN`、`UNSUPPORTED_FILE_TYPE`、`DECODE_FAILED`、`NO_AUDIO_STREAM`、`ZIP_INVALID`、`ZIP_EMPTY`、`JSONL_PARSE_FAILED`、`JSON_PARSE_FAILED`、`XML_PARSE_FAILED`、`DEPENDENCY_UNAVAILABLE`、`RECORD_SCHEMA_INVALID`。

## 4. Manifest（`manifest.json`）

按 `docs/算子开发/schemas/manifest.schema.json`：

- `inputFingerprint`：单文件按 `file+size+sha256`；目录/zip 按成员相对路径+大小+SHA-256 聚合；
- `sampleCount = successCount + failedCount`（视频含音轨按视频+音轨两个单元计）；
- `modelVersion=null`、`treeVersion=null`：本算子不加载模型、不消费分类树；
- `outputBytes/compressionRatio` 统计 payload 产物，不含 `manifest.json`/`summary.json` 自身；
- `artifacts[]` 每项含 `type/path/sha256/bytes`。

## 5. 样例

`dataset/sample/hello_corpus.txt` 为自建可运行样例；完整四模态样例见
`docs/算子开发/samples/`（来源与授权登记见 `SOURCES.md`，效果验收前需人工确认 H-04/H-05）。
