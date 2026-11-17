# 工作包回执 · dm-taxonomy-labeling（领域/能力多标签）

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
- 结果目录：`operator/dm-taxonomy-labeling/output/evidence/e53b5d9093388fe5/`（同次运行副本，原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-taxonomy-labeling/e53b5d9093388fe5`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 426 |
| successCount | 420 |
| failedCount | 6 |
| paramsHash | sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | bge-base-zh-v1.5 |
| treeVersion | taxonomy-1013-pending |

完整指标：
```json
{
 "treeVersion": "taxonomy-1013-pending",
 "labelSpaceSizes": {
  "domain": 209,
  "ability": 65
 },
 "spacesSeparated": true,
 "textRecords": 426,
 "skippedNonText": 6,
 "labeledCounts": {
  "domain": 382,
  "ability": 400
 },
 "unknownCounts": {
  "domain": 44,
  "ability": 26
 },
 "meanLabelsPerRecord": {
  "domain": 1.325,
  "ability": 1.272
 },
 "meanConfidence": {
  "domain": 0.400124,
  "ability": 0.468321
 },
 "pathLegalRate": 1.0,
 "unknownLabel": "未明确",
 "modelVersion": "bge-base-zh-v1.5",
 "annotation": {
  "accuracy": null,
  "blockedReason": "MATCHING_ANNOTATION_REQUIRED",
  "note": "无人工标注（H-05）；不填准确率/混淆矩阵。"
 },
 "provisional": true,
 "generatedAt": "2026-11-17T10:23:23+08:00"
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

