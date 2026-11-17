# 工作包回执 · OP-14（质量、一致性与难度）

## 状态
完成（本机真实样例链路）；效果验收待人工真值与阈值确认（H-03/H-05），不阻塞后续阶段。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-quality-analysis/output/evidence/f979e048a3250253/`（原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-quality-analysis/f979e048a3250253`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input_manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 432 |
| successCount | 432 |
| failedCount | 0 |
| paramsHash | sha256:8c383e416eb64356b8dda21151a5f0c39be2c019b78543957cb595912da92dc6 |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | rule-based-quality-v1 |
| treeVersion | None |

完整指标：
```json
{
 "records": 432,
 "completeness": {
  "mean": 1.0,
  "lowCompletenessCount": 0,
  "missingFieldCounts": {},
  "blankTextCount": 0
 },
 "conflict": {
  "candidateRecords": 426,
  "nearDuplicateGroups": 4,
  "nearDuplicateMembers": 8,
  "conflictGroups": 1,
  "conflictRate": 0.25,
  "conflictSamples": [
   {
    "members": [
     "r_3588b8ac64de03b837d32fe2",
     "r_93d4968b9919ade7b31bd4d1"
    ],
    "texts": 2
   }
  ],
  "minTextChars": 20,
  "nearDuplicateDistance": 3
 },
 "gini": {
  "status": "ok",
  "gini": 0.586985,
  "threshold": 0.6,
  "exceedsThreshold": false,
  "labelCount": 66,
  "instanceCount": 278,
  "topLabels": [
   {
    "path": "对话与交互/指令与训练/RLHF数据",
    "count": 40,
    "share": 0.143885
   },
   {
    "path": "结构化数据/交易与行为记录/用户行为日志与点击流",
    "count": 33,
    "share": 0.118705
   },
   {
    "path": "日志与遥测/告警与事件记录/告警记录",
    "count": 16,
    "share": 0.057554
   },
   {
    "path": "知识与参考/科普与专著/工具书与年鉴",
    "count": 13,
    "share": 0.046763
   },
   {
    "path": "知识与参考/百科词条/百科条目",
    "count": 11,
    "share": 0.039568
   },
   {
    "path": "知识与参考/科普与专著/学术专著",
    "count": 11,
    "share": 0.039568
   },
   {
    "path": "知识与参考/网页与博客/网页正文",
    "count": 11,
    "share": 0.039568
   },
   {
    "path": "行为与事件/人体动作/搬运与交互动作",
    "count": 11,
    "share": 0.039568
   },
   {
    "path": "代码与技术文档/程序代码/各语言源代码与脚本",
    "count": 10,
    "share": 0.035971
   },
   {
    "path": "专业与行业文档/学术论文与科研资料/实验报告",
    "count": 9,
    "share": 0.032374
   }
  ]
 },
 "annotation": {
  "status": "ok",
  "records": 432,
  "labeledRecords": 278,
  "coverage": 0.643519,
  "unlabeledRecords": 154,
  "level1Distribution": {
   "知识与参考": 53,
   "对话与交互": 49,
   "结构化数据": 46,
   "日志与遥测": 23,
   "行为与事件": 21,
   "专业与行业文档": 20,
   "代码与技术文档": 15,
   "教育与培训": 15,
   "三维与空间": 6,
   "自然与生态": 5,
   "专业影像": 4,
   "人文与历史": 4,
   "语音与人声": 3,
   "专业过程视频": 2,
   "人物与人体": 2,
   "图表与界面图像": 2,
   "社会与群体": 2,
   "艺术与设计": 2,
   "影视与娱乐": 1,
   "文学与创作内容": 1,
   "新闻与资讯": 1,
   "社交与社区内容": 1
  }
 },
 "multimodalConsistency": {
  "status": "ok",
  "pairs": 1,
  "bothLabeled": 0,
  "consistent": 0,
  "consistency": null
 },
 "difficulty": {
  "counts": {
   "中等": 143,
   "困难": 27,
   "简单": 2,
   "较难": 254
  },
  "bands": [
   {
    "level": "简单",
    "max": 25
   },
   {
    "level": "中等",
    "max": 50
   },
   {
    "level": "较难",
    "max": 75
   },
   {
    "level": "困难",
    "max": 100
   }
  ],
  "weights": {
   "sentenceLength": 0.4,
   "clauseComplexity": 0.3,
   "lexicalRarity": 0.3
  }
 },
 "polarity": {
  "counts": {
   "negative": 24,
   "neutral": 395,
   "positive": 7
  },
  "shares": {
   "neutral": 0.92723,
   "negative": 0.056338,
   "positive": 0.016432
  },
  "balance": 0.960094,
  "method": "lexicon + negation (rule-based)"
 },
 "lowQualityCount": 0,
 "failedCount": 0,
 "failuresByReason": {},
 "treeVersion": null,
 "provisional": true,
 "deterministic": true,
 "runtimeSec": 0.204,
 "generatedAt": "2026-11-17T10:51:50+08:00"
}
```

- 效果类指标无人工真值时写 `null` + `blockedReason`；本算子指标全部来自真实记录/媒体。
- 无随机数/常量伪造。

## 未决问题
- 阻塞项：无。
- 需人工确认：H-03 阈值口径、H-05 人工标注、H-06 模型/权重许可、H-02 树版本。
- 已知限制：见算子 README。

## 补充
- runId：`f979e048a3250253`
- inputFingerprint：`sha256:aed8d3843572719e3c4589ed538a44105424573efd814d26d903618feb4e62c9`
- paramsHash：`sha256:8c383e416eb64356b8dda21151a5f0c39be2c019b78543957cb595912da92dc6`
- seed：42
- operatorVersion：0.1.0
- 上游输入：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7`

