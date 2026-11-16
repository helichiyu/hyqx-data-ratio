# 工作包回执 · dm-multimodal-labeling

## 状态
完成（本机真实产物）

## 变更文件
- 见 git 提交 `feat(s2)` 的 diff。

## 运行命令
```bash
python - <<PY
import sys; sys.path.insert(0,"operator"); import inference
core=inference._import_operator_core("dm-multimodal-labeling")
core.run("operator/dm-corpus-normalization/output/evidence/10a342ae92595ab7", {}, 42, "operator/runtime/output/op05-run")
PY
```

## 证据路径
- 结果目录：`operator/dm-multimodal-labeling/output/evidence/7c549c29811c8574/`
- 指标文件：`metrics.json`
- 日志：`logs/service.log`（直接调用 core.run，无 HTTP 服务日志）
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| labeledRate | 0.643519 |
| modelVersion | bge-base-zh-v1.5 |
| treeVersion | taxonomy-1013-pending |
| labelSpaceSize | 279 |
| labeledCounts | {"audio": 1, "image": 1, "text": 275, "video": 1} |
| annotation | {"accuracy": null, "blockedReason": "MATCHING_ANNOTATION_REQUIRED", "confusionMatrix": null, "note": "无人工标注（H-05）；不填准确率/区间/混淆矩阵。", "samplesPerModal": {}, "wilsonLower": null, "wilsonUpper": null} |
| unclassifiedByReason | {"UNCLASSIFIED_LOW_CONFIDENCE": 35, "UNCLASSIFIED_LOW_SIMILARITY": 4, "UNCLASSIFIED_NO_SPEECH": 1, "UNCLASSIFIED_SMALL_MARGIN": 114} |

- 效果指标（与人工标注比对）：`null`，`blockedReason=MATCHING_ANNOTATION_REQUIRED`（H-05）。
- 证据来自真实模型/真实样例；无随机数/常量伪造。

## 未决问题
- 阻塞项：无（本机链路）。
- 需人工确认：H-02 树版本、H-05 人工标注、H-06 模型许可与算力、Docker/容器探针（H-01）。
- 已知限制：零样本 bge 标签向量 + OCR/ASR 证据；无人工标注，准确率为 null；音频无语音/OCR 无文字进未归类池。

## 下一步
人工标注到位后补准确率/Wilson/混淆矩阵；阶段门禁复核。
