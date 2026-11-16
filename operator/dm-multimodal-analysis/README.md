# OP-01 多模态识别与解析（`dm-multimodal-analysis`）

- 语义编码：`corpus_ingest_multimodal_parse_v1`
- 阶段/优先级：S1 / P0
- 版本：`0.1.0`
- 入口：单镜像 `op-data-mixing` 内的 `/{operatorId}/...`，HTTP 层由仓库根 `inference.py` 统一实现

## 1. 用途与边界

**用途**：判定一个批次中每个文件的模态（文本/图像/音频/视频），完成四模态解析、格式元数据抽取、解析质量统计、混合文件拆流清单和失败原因登记，输出标准记录供 OP-02 消费。

**做**：

- 扩展名 + 文件头魔数 + 容器特征交叉验证，输出 `modal/confidence/evidence/conflicts`；
- 文本：编码探测（UTF-8/GB18030/Big5/Latin-1）、乱码率、jsonl/json/xml/csv/txt 逐条抽取；
- PDF：PyMuPDF 页文本、扫描页识别、页统计、字号分布；
- 图像：Pillow 头信息、EXIF、ICC、DPI、解码校验、pHash；
- 音频：ffmpeg 流探测、16 kHz mono WAV、流式 VAD（语音/静音占比）；
- 视频：ffmpeg 流探测、关键帧与真实时间戳、音轨拆流为 16 kHz mono WAV；
- zip：防御性展开（basename、白名单、成员数/解压总量限制）；
- 失败样本逐条写 `reasonCode`，不静默丢弃。

**不做**：

- 不做打标、聚类、画像、配比、打包、评测（OP-02 之后）；
- 不接入 OCR/ASR/CLIP 模型；扫描页只统计、不伪造 OCR 文本；
- 不做平台 CRUD、对象存储落库、任务状态机；
- 不产出需要人工真值的准确率/F1（无标注时 `metrics` 不填效果指标）。

## 2. 接口

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/{operatorId}/healthz` | GET | `ready` 不含权重；返回 `weightsOk/dependencyStatus` |
| `/{operatorId}/uploadFile` | POST | multipart `file`，可选 `uniqueId` |
| `/{operatorId}/predict` | POST | JSON `{uniqueId/inputFile, params, seed}` 或 multipart |
| `/{operatorId}/downloadFile` | GET | `?path=<绝对路径>`，目录打 zip |
| `/{operatorId}/removeFile` | POST | `{path}` 或 `{uniqueId}`，幂等 |

`params`（均可选）：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `dt_source` | `file_time` | `file_time` / `ingest_time` / `content_time`；分区 `dt` 口径（待业务确认） |
| `max_keyframes` | 24 | 每个视频最多抽帧数 |
| `extract_audio` | true | 是否拆出视频音轨 |
| `ocr_enabled` | true | 预留；后端不可用时仍标 `OCR_BACKEND_UNAVAILABLE` |
| `max_file_bytes` | 512 MiB | 单文件解析上限 |

`seed` 缺省 42 并写回结果；本算子无随机过程，重跑结果一致（时间戳字段除外）。

## 3. 输出

输出目录：`OUTPUT_DIR/dm-multimodal-analysis/<runId>/`

| 文件 | 内容 |
| --- | --- |
| `result.jsonl` | 标准记录，逐条一行（Schema：`docs/算子开发/schemas/record.schema.json`） |
| `manifest.json` | 输入指纹、版本四件套、条数、字节、压缩比、产物 SHA-256 |
| `metrics.json` | 模态/来源计数、文本空值率/乱码率、PDF 扫描页、媒体统计、失败原因分布 |
| `failures.jsonl` | 失败样本 `{id, reasonCode, detail}` |
| `split_manifest.json` | 逐文件拆流清单（archive 成员、PDF 页、视频音轨、关键帧） |
| `input_manifest.json` | 输入成员、大小、SHA-256、指纹 |
| `summary.json` | 汇总信封（与 `predict` 返回一致） |
| `streams/audio/*.wav` | 音频 16 kHz mono WAV |
| `streams/video/keyframes/<rid>/*.jpg` | 视频关键帧 |
| `streams/video/audio_streams/<rid>.wav` | 视频音轨拆流 |

## 4. 指标口径

| 指标 | 口径 |
| --- | --- |
| `emptyTextRate` | 规范化前 `text.strip()==""` 的记录数 / 有文本字段的记录数 |
| `mojibakeRate` | 乱码记录数 / 文本记录数；单条乱码率 =（U+FFFD + C0 控制字符 + `Ã/Â/â€`）/ 字符数，阈值 2% |
| `decodeFailureRecords` | `quality.decodeError` 非空的记录数（如 UTF-8 失败后 Latin-1 兜底） |
| `pdf.scannedPages` | 页文本 <10 字符且页面含图像的非空页数 |
| `pdf.completeness` | 有文本页数 / 总页数 |
| `media.silentAudio` | VAD 静音占比 ≥99% 的音频文件数 |
| `detection.lowConfidenceFiles` | 置信度 <0.6 的文件数（当前样本为 0） |
| `failureRate` | 失败单元数 / 尝试单元数（视频含音轨按 2 个单元计） |

**未评测**：模态判定/属性抽取与人工标注的准确率（无人工标注，H-05）；OCR 准确率（无 OCR 后端）。均不填数字。

## 5. 复算命令

```bash
# 全量样例批次（四模态 + PDF + 混合 zip）
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-multimodal-analysis")
result = core.run("docs/算子开发/samples", params={}, seed=42,
                  output_dir="operator/runtime/output/manual-op01")
print(result["runId"], result["sampleCount"], result["successCount"], result["failedCount"])
PY
```

复算条件：输入指纹 + `operatorVersion` + `paramsHash` + `seed` 一致时，`result.jsonl` 与媒体产物哈希一致（`manifest.json` 的 `createdAt` 除外）。

## 6. 测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-multimodal-analysis/tests -q
"D:/anaconda3/envs/use/python.exe" -m pytest tests operator/_template/tests -q
```

覆盖：模态判定（扩展名/魔数/冲突）、编码与乱码、jsonl 边界、SimHash/pHash 确定性、来源规则、分区口径、真实四模态样例、混合 zip 拆流、PDF 扫描页、失败 reasonCode、空目录、坏 zip、Schema 校验、幂等。

## 7. 已知限制

1. **无 OCR 后端**：PDF 扫描页只统计并标 `OCR_BACKEND_UNAVAILABLE`，不产出 OCR 文本；
2. **无 ASR**：音频/视频只出转写占位（`text=null`），ASR 在 OP-11；
3. **ffprobe 未装**：流信息由 `ffmpeg -i` stderr 解析；`frameCount` 为 `duration*fps` 近似值，已标 `frameCountSource`；
4. **分区 `dt` 默认取文件修改时间**，业务口径待确认（H-03/Q-01 相邻项）；
5. `metadata.extra.sourcePath` 写入绝对路径，便于 OP-02 溯源；离线迁移时按新路径重新解析；
6. 文本单条超过 2000 万字符会被截断并标 `TEXT_TRUNCATED`。

## 8. 版本与证据

- 代码版本：`0.1.0`；`modelVersion=null`、`treeVersion=null`（本算子不加载模型、不消费分类树）；
- 证据目录：`operator/dm-multimodal-analysis/output/evidence/<runId>/`（9 件套 + `split_manifest.json`）。
