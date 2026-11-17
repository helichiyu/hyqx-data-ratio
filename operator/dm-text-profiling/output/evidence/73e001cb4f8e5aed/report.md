# 工作包回执 · OP-10（文本属性与任务适配）

## 状态
完成（本机真实样例链路）；效果验收待人工真值与阈值确认（H-03/H-05），不阻塞后续阶段。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-text-profiling/output/evidence/73e001cb4f8e5aed/`（原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-text-profiling/73e001cb4f8e5aed`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input_manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 426 |
| successCount | 426 |
| failedCount | 0 |
| paramsHash | sha256:332106052eff02f9ec0ae7aa917246d9726e2fcf0e84a3b0d726a02050acfc34 |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | rule-based-text-metrics-v1 |
| treeVersion | None |

完整指标：
```json
{
 "textRecords": 426,
 "skippedNonText": 6,
 "evaluatedRecords": 426,
 "failedCount": 0,
 "failuresByReason": {},
 "genreCounts": {
  "general": 348,
  "academic": 78
 },
 "distributions": {
  "sentenceCompleteness": {
   "p50": 0.0,
   "p90": 7.5,
   "p99": 8.88889
  },
  "clauseComplexity": {
   "p50": 3.75,
   "p90": 10.0,
   "p99": 10.0
  },
  "lexicalRichness": {
   "p50": 9.28571,
   "p90": 10.0,
   "p99": 10.0
  },
  "informationDensity": {
   "p50": 6.321839,
   "p90": 7.733813,
   "p99": 8.602151
  },
  "domainMatch": {
   "p50": 3.483725,
   "p90": 5.66573,
   "p99": 7.96631
  },
  "genreFit": {
   "p50": 0.0,
   "p90": 1.66667,
   "p99": 1.66667
  },
  "overall": {
   "p50": 4.688256,
   "p90": 5.709307,
   "p99": 7.138833
  }
 },
 "lowFitCount": 4,
 "lowFitThreshold": 3.0,
 "weights": {
  "groupWeights": {
   "structure": 0.4,
   "semantic": 0.3,
   "domain": 0.3
  },
  "subWeights": {
   "structure": {
    "sentenceCompleteness": 0.5,
    "clauseComplexity": 0.5
   },
   "semantic": {
    "lexicalRichness": 0.6,
    "informationDensity": 0.4
   },
   "domain": {
    "domainMatch": 0.7,
    "genreFit": 0.3
   }
  }
 },
 "domainMatchStatus": "ok",
 "domainMatchReasonCode": null,
 "treeVersion": null,
 "provisional": true,
 "deterministic": true,
 "runtimeSec": 0.791,
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
- runId：`73e001cb4f8e5aed`
- inputFingerprint：`sha256:aed8d3843572719e3c4589ed538a44105424573efd814d26d903618feb4e62c9`
- paramsHash：`sha256:332106052eff02f9ec0ae7aa917246d9726e2fcf0e84a3b0d726a02050acfc34`
- seed：42
- operatorVersion：0.1.0
- 上游输入：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`

