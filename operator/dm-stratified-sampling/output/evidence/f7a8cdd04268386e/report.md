# 工作包回执 · OP-04（分层抽样）

## 状态
完成（本机真实样例链路）；效果验收待人工真值与阈值确认（H-03/H-05），不阻塞后续阶段。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-stratified-sampling/output/evidence/f7a8cdd04268386e/`（原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-stratified-sampling/f7a8cdd04268386e`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input_manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 432 |
| successCount | 86 |
| failedCount | 0 |
| paramsHash | sha256:031efcf546b1067cf2f86f27bdd7f82ab74da0833210a8f7603082e73916413a |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | None |
| treeVersion | None |

完整指标：
```json
{
 "population": 432,
 "target": 86,
 "allocated": 86,
 "sampled": 86,
 "shareUsed": 0.2,
 "shareBand": "small",
 "shareRules": {
  "large": {
   "min": 0.05,
   "max": 0.1,
   "thresholdRecords": 100000
  },
  "small": {
   "min": 0.2,
   "max": 0.3,
   "default": 0.2
  }
 },
 "targetMet": true,
 "allocationBasis": "neyman",
 "unmetQuota": 0,
 "minTotal": 100000,
 "minTotalMet": false,
 "stratumCount": 56,
 "duplicateFree": true,
 "actualRatio": 0.199074,
 "maxAbsBias": 0.085486,
 "unmetStrata": [],
 "skippedDimensions": {
  "cluster": "provided",
  "quality": "provided"
 },
 "failedCount": 0,
 "seed": 42,
 "provisional": true,
 "deterministic": true,
 "runtimeSec": 0.0,
 "generatedAt": "2026-11-17T10:53:32+08:00"
}
```

- 效果类指标无人工真值时写 `null` + `blockedReason`；本算子指标全部来自真实记录/媒体。
- 无随机数/常量伪造。

## 未决问题
- 阻塞项：无。
- 需人工确认：H-03 阈值口径、H-05 人工标注、H-06 模型/权重许可、H-02 树版本。
- 已知限制：见算子 README。

## 补充
- runId：`f7a8cdd04268386e`
- inputFingerprint：`sha256:aed8d3843572719e3c4589ed538a44105424573efd814d26d903618feb4e62c9`
- paramsHash：`sha256:031efcf546b1067cf2f86f27bdd7f82ab74da0833210a8f7603082e73916413a`
- seed：42
- operatorVersion：0.1.0
- 上游输入：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`

