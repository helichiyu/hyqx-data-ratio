# 工作包回执 · dm-multimodal-labeling（多模态自动打标）

## 状态
完成（本机真实样例链路）；效果验收待人工真值（H-05），不阻塞后续阶段。

## 变更文件
- 新增：见 git 提交 `feat(s2)` 的 diff。
- 修改：`operator/map.json`、`docs/算子开发/registry.json`、任务书第 10 节。
- 删除：无。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s2_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-multimodal-labeling/output/evidence/e53b5d9093388fe5/`（同次运行副本，原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-multimodal-labeling/e53b5d9093388fe5`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 432 |
| successCount | 278 |
| failedCount | 154 |
| paramsHash | sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | bge-base-zh-v1.5 |
| treeVersion | taxonomy-1013-pending |

完整指标：
```json
{
 "modalityCounts": {
  "audio": 3,
  "image": 1,
  "text": 426,
  "video": 2
 },
 "labeledCounts": {
  "audio": 1,
  "image": 1,
  "text": 275,
  "video": 1
 },
 "unclassifiedCounts": {
  "audio": 2,
  "text": 151,
  "video": 1
 },
 "labeledRate": 0.643519,
 "meanConfidenceByModal": {
  "audio": 0.312253,
  "image": 0.42514,
  "text": 0.4242,
  "video": 0.376989
 },
 "meanEvidenceCharsByModal": {
  "audio": 19.0,
  "image": 1014.0,
  "text": 256.716,
  "video": 755.0
 },
 "labelSpaceSize": 279,
 "treeVersion": "taxonomy-1013-pending",
 "modelVersion": "bge-base-zh-v1.5",
 "topK": 5,
 "confidenceThreshold": 0.25,
 "marginThreshold": 0.005,
 "pathLegalRate": 1.0,
 "unclassifiedByReason": {
  "UNCLASSIFIED_LOW_CONFIDENCE": 35,
  "UNCLASSIFIED_LOW_SIMILARITY": 4,
  "UNCLASSIFIED_NO_SPEECH": 1,
  "UNCLASSIFIED_SMALL_MARGIN": 114
 },
 "toolErrors": {},
 "evidenceSources": {
  "text": 426,
  "ocrImages": 1,
  "asrAudios": 3,
  "videoFusion": 2
 },
 "toolVersions": {
  "rapidocr": "1.4.4",
  "funasr": "1.4.16",
  "transformers": "4.43.4"
 },
 "annotation": {
  "accuracy": null,
  "wilsonLower": null,
  "wilsonUpper": null,
  "confusionMatrix": null,
  "samplesPerModal": {},
  "blockedReason": "MATCHING_ANNOTATION_REQUIRED",
  "note": "无人工标注（H-05）；不填准确率/区间/混淆矩阵。"
 },
 "provisional": true,
 "generatedAt": "2026-11-17T10:22:47+08:00"
}
```

- 与人工标注比对的准确率/F1/Wilson/混淆矩阵：`null`（无人工真值，blockedReason=MATCHING_ANNOTATION_REQUIRED / REVIEW_RECORDS_REQUIRED）。
- 证据全部来自真实样例与真实模型推理；无随机数/常量伪造。

## 未决问题
- 阻塞项：无。
- 需人工确认：H-02 树版本（`taxonomy-1013-pending`）、H-03 阈值口径（联调初值）、H-05 人工标注、H-06 模型许可证。
- 已知限制：见 `metrics.provisional` 与算子 README。

## 补充
- runId：`e53b5d9093388fe5`
- inputFingerprint：`sha256:aed8d3843572719e3c4589ed538a44105424573efd814d26d903618feb4e62c9`
- paramsHash：`sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
- seed：42
- operatorVersion：0.1.0
- 上游输入：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`

