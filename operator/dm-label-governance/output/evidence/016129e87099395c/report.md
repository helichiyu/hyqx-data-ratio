# 工作包回执 · dm-label-governance（标签治理）

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
- 结果目录：`operator/dm-label-governance/output/evidence/016129e87099395c/`（同次运行副本，原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-label-governance/016129e87099395c`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 432 |
| successCount | 432 |
| failedCount | 0 |
| paramsHash | sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | None |
| treeVersion | taxonomy-1013-pending |

完整指标：
```json
{
 "treeVersion": "taxonomy-1013-pending",
 "records": 432,
 "labels": 278,
 "illegalLabels": 0,
 "legalRate": 1.0,
 "conflicts": 0,
 "piiRecords": 1,
 "unclassifiedRecords": 154,
 "unclassifiedByReason": {
  "UNCLASSIFIED_LOW_CONFIDENCE": 35,
  "UNCLASSIFIED_LOW_SIMILARITY": 4,
  "UNCLASSIFIED_NO_SPEECH": 1,
  "UNCLASSIFIED_SMALL_MARGIN": 114
 },
 "suggestionsByType": {},
 "reviewMetrics": {
  "kappa": null,
  "alpha": null,
  "accuracy": null,
  "adoptionRate": null,
  "modificationRate": null,
  "blockedReason": "REVIEW_RECORDS_REQUIRED",
  "note": "无人工审核记录（H-05）；不填 Kappa/准确率/采纳率。"
 },
 "modelVersion": null,
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
- runId：`016129e87099395c`
- inputFingerprint：`sha256:09da4bd4f21d6e7e6935a751ec25a2af5361bc980cac546b48e675bb86394c29`
- paramsHash：`sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
- seed：42
- operatorVersion：0.1.0
- 上游输入：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-multimodal-labeling/e53b5d9093388fe5`

