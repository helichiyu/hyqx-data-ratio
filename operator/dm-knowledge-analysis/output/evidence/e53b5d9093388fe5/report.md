# 工作包回执 · OP-13（知识覆盖、热点与风格）

## 状态
完成（本机真实样例链路）；效果验收待人工真值与阈值确认（H-03/H-05），不阻塞后续阶段。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-knowledge-analysis/output/evidence/e53b5d9093388fe5/`（原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-knowledge-analysis/e53b5d9093388fe5`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input_manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 426 |
| successCount | 426 |
| failedCount | 0 |
| paramsHash | sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | rule-based-knowledge-v1 |
| treeVersion | None |

完整指标：
```json
{
 "textRecords": 426,
 "skippedNonText": 6,
 "evaluatedRecords": 426,
 "failedCount": 0,
 "failuresByReason": {},
 "terms": {
  "status": "unavailable",
  "reasonCode": "GLOSSARY_UNAVAILABLE",
  "glossaryTerms": 0,
  "matchedTerms": 0,
  "corpusCoverage": null,
  "coverageMean": null,
  "densityMeanPer100Chars": null
 },
 "entityCoverage": {
  "status": "unavailable",
  "reasonCode": "KG_UNAVAILABLE",
  "note": "未提供知识图谱/实体词表，不产出实体覆盖率。"
 },
 "knowledgeTypes": {
  "counts": {
   "creative": 7,
   "fact": 2,
   "reasoning": 1,
   "unknown": 416
  },
  "shares": {
   "unknown": 0.976526,
   "creative": 0.016432,
   "fact": 0.004695,
   "reasoning": 0.002347
  },
  "method": "keyword-rule hit share"
 },
 "styles": {
  "counts": {
   "academic": 78,
   "general": 348
  },
  "shares": {
   "general": 0.816901,
   "academic": 0.183099
  }
 },
 "hotspot": {
  "windowDays": 365,
  "counts": {
   "hot": 15,
   "long_tail": 234,
   "unknown": 177
  },
  "asOf": "2026-12-31"
 },
 "provisional": true,
 "deterministic": true,
 "runtimeSec": 0.016,
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
- runId：`e53b5d9093388fe5`
- inputFingerprint：`sha256:aed8d3843572719e3c4589ed538a44105424573efd814d26d903618feb4e62c9`
- paramsHash：`sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
- seed：42
- operatorVersion：0.1.0
- 上游输入：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`

