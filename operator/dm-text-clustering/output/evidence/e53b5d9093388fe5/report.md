# 工作包回执 · dm-text-clustering（句向量与主题聚类）

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
- 结果目录：`operator/dm-text-clustering/output/evidence/e53b5d9093388fe5/`（同次运行副本，原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-text-clustering/e53b5d9093388fe5`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input-manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 426 |
| successCount | 426 |
| failedCount | 0 |
| paramsHash | sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | bge-base-zh-v1.5 |
| treeVersion | None |

完整指标：
```json
{
 "recordsRead": 432,
 "textRecords": 426,
 "skippedNonText": 6,
 "clusteredRecords": 426,
 "failedCount": 0,
 "chunkCount": 488,
 "avgChunksPerRecord": 1.146,
 "vectorDimension": 768,
 "storageDtype": "float16",
 "modelVersion": "bge-base-zh-v1.5",
 "k": 15,
 "silhouette": 0.04762,
 "searchRange": {
  "lower": 15,
  "upper": 64,
  "n": 426
 },
 "searchCandidates": 17,
 "clusterSizes": {
  "min": 4,
  "median": 27.0,
  "max": 64,
  "mean": 28.4
 },
 "topicClusters": 15,
 "failuresByReason": {},
 "deterministic": true,
 "runtimeSec": 52.833,
 "provisional": true,
 "generatedAt": "2026-11-17T10:21:50+08:00"
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

