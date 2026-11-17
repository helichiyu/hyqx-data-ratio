# 工作包回执 · OP-09（语言、地域与时效画像）

## 状态
完成（本机真实样例链路）；效果验收待人工真值与阈值确认（H-03/H-05），不阻塞后续阶段。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-language-profiling/output/evidence/e53b5d9093388fe5/`（原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-language-profiling/e53b5d9093388fe5`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input_manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 432 |
| successCount | 432 |
| failedCount | 0 |
| paramsHash | sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | unicode-script-heuristics-v1 |
| treeVersion | None |

完整指标：
```json
{
 "language": {
  "counts": {
   "en": 420,
   "unknown": 6,
   "fr": 3,
   "es": 2,
   "de": 1
  },
  "shares": {
   "en": 0.972222,
   "unknown": 0.013889,
   "fr": 0.006944,
   "es": 0.00463,
   "de": 0.002315
  },
  "statusCounts": {
   "identified": 426,
   "unknown": 6
  },
  "confidenceMean": 0.986111,
  "minConfidence": 0.85,
  "method": "unicode-script + function-words (rule-based)"
 },
 "time": {
  "yearCounts": {
   "1905": 1,
   "1950": 2,
   "1956": 1,
   "1959": 3,
   "1960": 1,
   "1961": 1,
   "1964": 1,
   "1965": 1,
   "1973": 1,
   "1980": 2,
   "1981": 2,
   "1982": 2,
   "1983": 1,
   "1988": 2,
   "1990": 1,
   "1991": 1,
   "1993": 2,
   "1994": 2,
   "1995": 4,
   "1997": 1,
   "1998": 4,
   "1999": 2,
   "2000": 2,
   "2001": 3,
   "2002": 3,
   "2003": 3,
   "2004": 4,
   "2006": 5,
   "2008": 2,
   "2009": 8,
   "2010": 7,
   "2011": 7,
   "2012": 9,
   "2013": 5,
   "2014": 2,
   "2015": 10,
   "2016": 11,
   "2017": 12,
   "2018": 16,
   "2019": 15,
   "2020": 18,
   "2021": 14,
   "2022": 10,
   "2023": 22,
   "2024": 8,
   "2025": 7,
   "2026": 8,
   "unknown": 183
  },
  "quarterCounts": {
   "2017-Q4": 1,
   "2018-Q4": 1,
   "2023-Q2": 1
  },
  "timeSourceCounts": {
   "text_iso_date": 3,
   "text_year": 246,
   "unknown": 183
  },
  "freshnessMean": 0.136546,
  "freshnessWeights": {
   "last_1y": 0.6,
   "last_3y": 0.3,
   "older": 0.1
  },
  "staleThreshold": 0.4,
  "staleCount": 234,
  "staleShare": 0.939759,
  "knownTimeRatio": 0.576389,
  "asOf": "2026-12-31"
 },
 "region": {
  "status": "unavailable",
  "reasonCode": "GEO_SOURCE_UNAVAILABLE",
  "note": "记录未提供 region/country/timezone 字段；不做 IP 或文本推断。"
 },
 "failedCount": 0,
 "failuresByReason": {},
 "provisional": true,
 "deterministic": true,
 "runtimeSec": 0.053,
 "generatedAt": "2026-11-17T10:51:49+08:00"
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

