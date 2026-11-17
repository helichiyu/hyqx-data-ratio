# 工作包回执 · OP-12（图像/视频属性）

## 状态
完成（本机真实样例链路）；效果验收待人工真值与阈值确认（H-03/H-05），不阻塞后续阶段。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-visual-analysis/output/evidence/e53b5d9093388fe5/`（原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-visual-analysis/e53b5d9093388fe5`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input_manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 3 |
| successCount | 3 |
| failedCount | 0 |
| paramsHash | sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | opencv-heuristics-v1 |
| treeVersion | None |

完整指标：
```json
{
 "mediaCounts": {
  "image": 1,
  "video": 2
 },
 "processedRecords": 3,
 "failedCount": 0,
 "failuresByReason": {},
 "image": {
  "count": 1,
  "entropyMean": 1.947062,
  "sharpnessMean": 755.438656
 },
 "video": {
  "count": 2,
  "dynamicFrameRatioMean": 0.921053,
  "meanShotDurationSecMean": 7.520834
 },
 "unavailable": {
  "scene": "SCENE_MODEL_UNAVAILABLE",
  "object": "OBJECT_MODEL_UNAVAILABLE",
  "action": "ACTION_MODEL_UNAVAILABLE",
  "audioVisualBleu": "REFERENCE_TRANSCRIPT_REQUIRED"
 },
 "modelVersion": "opencv-heuristics-v1",
 "provisional": true,
 "deterministic": true,
 "runtimeSec": 3.14,
 "generatedAt": "2026-11-17T10:52:02+08:00"
}
```

- 效果类指标无人工真值时写 `null` + `blockedReason`；本算子指标全部来自真实记录/媒体。
- 无随机数/常量伪造。

## 未决问题
- 阻塞项：无。
- 需人工确认：H-03 阈值口径、H-05 人工标注、H-06 模型/权重许可、H-02 树版本。
- 已知限制：见算子 README。

## 补充
- runId：`e53b5d9093388fe5`
- inputFingerprint：`sha256:aed8d3843572719e3c4589ed538a44105424573efd814d26d903618feb4e62c9`
- paramsHash：`sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
- seed：42
- operatorVersion：0.1.0
- 上游输入：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`

