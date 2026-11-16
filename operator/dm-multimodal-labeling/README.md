# OP-05 多模态自动打标（`dm-multimodal-labeling`）

- 语义编码：`corpus_label_multimodal_v1`
- 阶段/优先级：S2 / P0
- 版本：`0.1.0`
- 模型：`bge-base-zh-v1.5`（768 维，MIT）+ RapidOCR 1.4.4（Apache-2.0）+ FunASR paraformer-zh（Apache-2.0）

## 1. 用途与边界

**用途**：对文本/图像/音频/视频统一打标，输出可变深度路径、置信度、topK、证据、模型与树版本；低置信/无证据进未归类池。

**方法（零样本）**：

1. 内容证据：文本原文；图像 OCR；音频 ASR；视频关键帧 OCR + 音轨 ASR 融合（权重 0.5/0.5）。
2. 内容与标签统一用 bge 向量；候选标签 = 内容树叶子（279 个），标签文本为“路径 > 节点：描述”。
3. 余弦相似度 → topK（默认 5）内 softmax（T=0.02）得置信度；同时要求 top1 余弦 ≥0.45、top1-top2 ≥0.005，否则进未归类池。
4. 证据：OCR 逐条文本/坐标/置信度、ASR 转写片段、视频关键帧时间戳。

**不做**：

- 不训练/微调分类器；不调用 LLM；
- 不伪造无证据标签；不产出无人工标注的准确率/F1（`metrics.annotation.accuracy=null`）；
- 不做标签治理（OP-07）、领域/能力标签（OP-06）。

## 2. 接口与参数

五端点与平台一致。`input_path` 接受 OP-02 运行目录（`records.jsonl` + `standard/` + `index/`）或记录文件；媒体按 `index/metadata.parquet` 的 `standard_path` 定位，缺失时按约定路径回退。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `top_k` | 5 | 候选标签数（1–20） |
| `confidence_threshold` | 0.25 | topK 内 softmax 置信度下限 |
| `margin_threshold` | 0.005 | top1-top2 余弦差下限 |
| `ocr_enabled` / `asr_enabled` | true | 模态证据开关 |
| `max_records` | 100000 | 最多处理记录数 |
| `device` | cpu | 向量模型设备 |

`seed` 只在参数哈希与结果复算中使用；推理无随机过程。

## 3. 输出

```text
result.jsonl        # 每条：record_id/modal/labels[{path,confidence,topK,evidence,modelVersion,treeVersion}]/topK/unclassified/reasonCode
unclassified.jsonl  # 未归类样本与原因、topK、证据
failures.jsonl      # 未归类 + 工具错误（OCR/ASR/关键帧/媒体缺失）
label_vectors.npy   # 标签向量 (279,768) float16
label_ids.jsonl     # 行号→标签路径/名称/描述
metrics.json / manifest.json / input_manifest.json / summary.json
streams/keyframes/<record_id>/  # 视频关键帧
```

`outputFilePath` 指向 `result.jsonl`。

## 4. 指标口径

| 指标 | 口径 |
| --- | --- |
| `labeledRate` | 有至少一个标签的记录 / 全部记录 |
| `labeledCounts` / `unclassifiedCounts` | 按模态统计 |
| `meanConfidenceByModal` | 已打标记录 top1 置信度均值 |
| `meanEvidenceCharsByModal` | 已打标记录证据字符数均值 |
| `pathLegalRate` | 命中当前 `treeVersion` 的标签数 / 标签总数（应为 1.0） |
| `unclassifiedByReason` | `LOW_SIMILARITY` / `LOW_CONFIDENCE` / `SMALL_MARGIN` / `NO_TEXT_EVIDENCE` / `NO_SPEECH` |
| `toolVersions` | RapidOCR / FunASR / transformers 版本 |

**未评测**：准确率、Wilson 区间、混淆矩阵（无人工标注 H-05）；`annotation.blockedReason=MATCHING_ANNOTATION_REQUIRED`。

## 5. 复算命令

```bash
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import sys; sys.path.insert(0, "operator")
import inference
core = inference._import_operator_core("dm-multimodal-labeling")
result = core.run(
    "operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7",
    params={}, seed=42, output_dir="operator/runtime/output/manual-op05")
print(result["sampleCount"], result["successCount"], result["metrics"]["labeledRate"])
PY
```

相同输入/参数/seed 在同机、同模型版本下 `result.jsonl` 一致。

## 6. 测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-multimodal-labeling/tests -q
```

覆盖：树叶子路径、高置信/低相似度/小边际路由、向量融合、真实 OCR、文本打标幂等、四模态真实媒体、路径合法率、缺失媒体 reasonCode。

## 7. 已知限制

1. **零样本非训练分类器**：标签语义靠标签名/描述，专业长尾标签区分度有限；需人工验证与阈值确认（H-05/H-06）。
2. **音频无语音**：纯音乐/噪声无 ASR 文本 → `UNCLASSIFIED_NO_SPEECH`，不伪造。
3. **视频融合**：仅有 OCR 或仅有 ASR 时按可用证据加权；两者皆无 → 未归类。
4. **OCR/ASR 版本与许可**：RapidOCR/Apache-2.0、paraformer-zh/Apache-2.0；模型随镜像，运行期不联网。
5. **长音频**：单条 >5 分钟切片转写；单条 >30 分钟拒绝并提示平台分片。
6. **树版本**：`taxonomy-1013-pending`（H-02 待确认），变更后需重跑并保留旧结果追溯。

## 8. 版本与证据

- `operatorVersion=0.1.0`；`modelVersion=bge-base-zh-v1.5`；`treeVersion=taxonomy-1013-pending`；
- 证据目录：`operator/dm-multimodal-labeling/output/evidence/<runId>/`。
