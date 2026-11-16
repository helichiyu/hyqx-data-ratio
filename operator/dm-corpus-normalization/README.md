# OP-02 标准化、元数据与去重（`dm-corpus-normalization`）

- 语义编码：`corpus_ingest_normalize_index_v1`
- 阶段/优先级：S1 / P0
- 版本：`0.1.0`
- 入口：单镜像 `op-data-mixing` 内的 `/{operatorId}/...`，HTTP 层由仓库根 `inference.py` 统一实现

## 1. 用途与边界

**用途**：消费 OP-01 的标准记录与源文件，生成统一容器产物（文本 Parquet / WebP / 16 kHz mono WAV / H.264 MP4）、manifest、元数据宽表/索引、重复与异常清单、跨模态关联表。

**做**：

- 读取 OP-01 `result.jsonl`（只读文件契约，不 import OP-01 代码）；无 `result.jsonl` 时返回 `RECORDS_NOT_FOUND`；
- 记录校验（必填/枚举/哈希/分区格式）与文本归一化（NFC、去控制字符、折叠空行），重算 SimHash；
- 按 `modal/source/dt` 分区写 Parquet（zstd、row group 65536），写后回读校验条数；
- 图像 WebP、音频 16 kHz mono WAV、视频 H.264 转码（编码器不可用时流复制并标 `STANDARDIZATION_FALLBACK`）；
- 精确重复（MD5/SHA-256）+ SimHash 分带近重复 + 图像 pHash 近重复，输出 `duplicateOf` 不丢记录；
- 元数据宽表（JSONL + Parquet）、字段缺失清单、分区统计；
- 异常清单：空文本、解码错误、扫描页无 OCR、静音音频、黑帧、标准化降级；
- 跨模态关联：文件级（视频 ↔ 拆流音轨）+ 归档级（同一 zip 的模态构成）。

**不做**：

- 不做打标、聚类、画像、配比、打包、评测；
- 不做对象存储写入、数据库落库、报告渲染、任务状态机；
- 不调用人工标注；不产出准确率类效果指标；
- 不修改或删除 OP-01 产物（只读取）。

## 2. 接口

与全平台一致的五个端点（见 `docs/算子开发/算子工程契约.md`）。

`params`（均可选）：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `source_root` | 空 | 源文件根目录；记录里的 `sourcePath` 不可用时按 `<source_root>/<extra.file>` 定位 |
| `simhash_max_distance` | 3 | 文本近重复汉明距离阈值 |
| `phash_max_distance` | 8 | 图像近重复汉明距离阈值 |
| `max_records` | 1,000,000 | 单次最多处理记录数 |

`input_path` 可以是 OP-01 的运行目录（含 `result.jsonl`），也可以是 `result.jsonl` 文件本身。
平台侧推荐用 `inputFile` 直接指向 OP-01 的 `runDir`（在 `OUTPUT_DIR` 内，路径闸门允许）。

## 3. 输出

输出目录：`OUTPUT_DIR/dm-corpus-normalization/<runId>/`

```text
standard/parquet/modal=<m>/source=<s>/dt=<d>/part-0000.parquet   # zstd，含全部记录
standard/images/<record_id>.webp
standard/audio/<record_id>.wav                                   # 16 kHz mono
standard/video/<record_id>.mp4                                   # H.264；失败时原容器+告警
index/metadata.parquet                                           # 元数据宽表
index/metadata.jsonl 不存在时以 Parquet 为准；缺失字段见 missing_fields.json
index/missing_fields.json
index/partition_stats.json
records.jsonl          # 归一化后的记录（含 standardizationNotes / duplicateOf）
duplicates.jsonl       # {groupId, kind, representative, members, evidence}
anomalies.jsonl        # {recordId, type, detail, evidence?}
associations.jsonl     # {level: file|archive, key, modalities, ...}
failures.jsonl         # {id, reasonCode, detail}
manifest.json
metrics.json
input_manifest.json
summary.json
```

`predict` 的 `outputFilePath` 指向 `records.jsonl`。

## 4. 指标口径

| 指标 | 口径 |
| --- | --- |
| `sampleCount` | 读取的记录行数（含无效行） |
| `successCount` | 通过校验并生成索引的记录数（文本无需外部文件） |
| `failedCount` | 无效行 + 源文件缺失 + 标准化失败 |
| `parquet.rows` | 分区 Parquet 实际回读条数（写后校验） |
| `dedup.duplicateRecords` | 被标 `duplicateOf` 的记录数（不代表可删除） |
| `anomalies.*` | 各类型异常条数（同一记录可多类型） |
| `associations.fileGroups` | 文件级关联组数（视频+音轨） |
| `associations.archiveGroups` | 同一 zip 的多模态关联组数 |
| `decodeCheck` | 抽检比例 1%（至少 1 个）的媒体产物可解码数 |
| `normalization.changed` | 归一化前后文本有变化的记录数 |

**未评测**：去重准确率/召回率（无人工判定）、跨模态语义一致性（无真值）。不填数字。

## 5. 复算命令

```bash
# 1) 先跑 OP-01 得到运行目录（示例见 OP-01 README）
# 2) 用 OP-01 运行目录作为输入
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-corpus-normalization")
result = core.run("operator/runtime/output/manual-op01", params={}, seed=42,
                  output_dir="operator/runtime/output/manual-op02")
print(result["runId"], result["sampleCount"], result["successCount"], result["failedCount"])
PY
```

复算条件：上游 `result.jsonl` 指纹 + 本算子版本 + 参数 + seed 一致时，`records.jsonl`、Parquet 内容与媒体产物哈希一致（`manifest.createdAt` 除外）。

## 6. 测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-corpus-normalization/tests -q
"D:/anaconda3/envs/use/python.exe" -m pytest tests operator/_template/tests -q
```

覆盖：记录校验、文本归一化、精确/近重复、Parquet 写读、分区统计、跨模态关联、异常检测、消费 OP-01 真实产物、幂等、manifest 对账、源文件缺失、无记录输入。

## 7. 已知限制

1. **源文件依赖**：媒体记录必须能按 `metadata.extra.sourcePath` 或 `source_root` 找到源文件；缺失记 `SOURCE_FILE_MISSING`，不复制上游摘要冒充产物；
2. **视频转码**：ffmpeg 无 `libx264` 时退化为流复制；仍失败则复制原文件并标 `STANDARDIZATION_FALLBACK`，不声称已转码；
3. **索引引擎**：当前用 Parquet 宽表 + JSONL，未接 DuckDB/ES（平台资源决定，任务书 S1 风险项）；
4. **去重为启发式**：SimHash/pHash 阈值是联调初值，需按业务确认（H-03 相邻项）；
5. **大文件**：Parquet 按分区整批写入；百万级记录需按平台分片调用，避免单请求超时；
6. `metadata.extra.sourcePath` 为绝对路径，离线迁移后需重新解析上游。

## 8. 版本与证据

- 代码版本：`0.1.0`；`modelVersion/treeVersion` 沿用上游 manifest（无上游时为 `null`）；
- 证据目录：`operator/dm-corpus-normalization/output/evidence/<runId>/`（9 件套）。
