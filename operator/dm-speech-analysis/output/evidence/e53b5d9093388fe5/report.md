# 工作包回执 · OP-11（语音质量与声学属性）

## 状态
完成（本机真实样例链路）；效果验收待人工真值与阈值确认（H-03/H-05），不阻塞后续阶段。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-speech-analysis/output/evidence/e53b5d9093388fe5/`（原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-speech-analysis/e53b5d9093388fe5`）
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
| modelVersion | paraformer-zh |
| treeVersion | None |

完整指标：
```json
{
 "audioRecords": 3,
 "processedRecords": 3,
 "failedCount": 0,
 "failuresByReason": {},
 "transcribedRecords": 2,
 "speechRatioMean": 0.797561,
 "pitchMeanHz": 222.511491,
 "werMean": null,
 "cerMean": null,
 "werStatus": "unavailable",
 "werReasonCode": "REFERENCE_TEXT_REQUIRED",
 "lowQualityCount": 1,
 "lowQualityReasons": {
  "ASR_EMPTY": 1
 },
 "thresholds": {
  "werLowQuality": 0.2,
  "cerLowQuality": 0.3,
  "minSpeechRatio": 0.1
 },
 "accent": {
  "status": "unavailable",
  "reasonCode": "ACCENT_MODEL_UNAVAILABLE"
 },
 "modelVersion": "paraformer-zh",
 "provisional": true,
 "deterministic": false,
 "deterministicNote": "ASR 为神经模型推理，CPU 上结果稳定但不同硬件可能有细微差异。",
 "runtimeSec": 9.01,
 "generatedAt": "2026-11-17T10:51:59+08:00"
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

