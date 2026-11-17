# 工作包回执 · OP-08（规模、来源与领域画像）

## 状态
完成（本机真实样例链路）；效果验收待人工真值与阈值确认（H-03/H-05），不阻塞后续阶段。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s3_chain.py --op02-dir "operator/runtime/transport/output/dm-corpus-normalization/10a342ae92595ab7"
```

## 证据路径
- 结果目录：`operator/dm-corpus-profiling/output/evidence/73e001cb4f8e5aed/`（原始运行目录 `E:/HYQX/数据配比/operator/runtime/transport/output/dm-corpus-profiling/73e001cb4f8e5aed`）
- 指标文件：`metrics.json`
- 日志：`logs/service.log`
- 样例输入：`input_manifest.json`

## 指标
| 指标 | 值 |
| --- | --- |
| sampleCount | 432 |
| successCount | 432 |
| failedCount | 0 |
| paramsHash | sha256:332106052eff02f9ec0ae7aa917246d9726e2fcf0e84a3b0d726a02050acfc34 |
| seed | 42 |
| operatorVersion | 0.1.0 |
| modelVersion | None |
| treeVersion | taxonomy-1013-pending |

完整指标：
```json
{
 "scale": {
  "recordCount": 432,
  "modalCounts": {
   "audio": 3,
   "image": 1,
   "text": 426,
   "video": 2
  },
  "textChars": 188345,
  "textBytes": 190607,
  "durationSec": 36.36,
  "frameCount": 361,
  "sizeBytes": 6600482,
  "standardBytes": 1661004,
  "standardCompressionRatio": 0.251649,
  "standardMissing": 0,
  "percentiles": {
   "textChars": {
    "p50": 189.0,
    "p90": 612.0,
    "p99": 1165.0
   },
   "durationSec": {
    "p50": 7.92,
    "p90": 10.01,
    "p99": 10.01
   },
   "frameCount": {
    "p50": 121.0,
    "p90": 240.0,
    "p99": 240.0
   },
   "sizeBytes": {
    "p50": 196.0,
    "p90": 673.0,
    "p99": 253642.0
   },
   "method": "nearest-rank：排序后取 ceil(p/100·N) 位"
  },
  "capturedAtPresent": 0
 },
 "sourceDistribution": {
  "shareSumPercent": 100.0,
  "corpusCredibility": 0.645205,
  "ahp": {
   "dimensions": [
    "authority",
    "transparency",
    "freshness",
    "evaluation"
   ],
   "weights": {
    "authority": 0.4,
    "transparency": 0.3,
    "freshness": 0.2,
    "evaluation": 0.1
   },
   "lambdaMax": 4.0,
   "ci": -0.0,
   "cr": 0.0,
   "consistencyMax": 0.1,
   "consistent": true
  },
  "classes": {
   "web_text": {
    "count": 307,
    "sharePercent": 71.064815,
    "credibility": 0.56,
    "dimensionScores": {
     "authority": 0.4,
     "transparency": 0.6,
     "freshness": 0.6,
     "evaluation": 1.0
    }
   },
   "books": {
    "count": 32,
    "sharePercent": 7.407407,
    "credibility": 0.819176,
    "dimensionScores": {
     "authority": 0.9,
     "transparency": 0.8,
     "freshness": 0.6,
     "evaluation": 0.991756
    }
   },
   "code": {
    "count": 0,
    "sharePercent": 0.0,
    "credibility": 0.69,
    "dimensionScores": {
     "authority": 0.8,
     "transparency": 0.9,
     "freshness": 0.5,
     "evaluation": 0.0
    }
   },
   "science": {
    "count": 86,
    "sharePercent": 19.907407,
    "credibility": 0.87,
    "dimensionScores": {
     "authority": 0.95,
     "transparency": 0.9,
     "freshness": 0.6,
     "evaluation": 1.0
    }
   },
   "wiki": {
    "count": 7,
    "sharePercent": 1.62037,
    "credibility": 0.825,
    "dimensionScores": {
     "authority": 0.8,
     "transparency": 0.95,
     "freshness": 0.6,
     "evaluation": 1.0
    }
   },
   "dialogue": {
    "count": 0,
    "sharePercent": 0.0,
    "credibility": 0.42,
    "dimensionScores": {
     "authority": 0.5,
     "transparency": 0.4,
     "freshness": 0.5,
     "evaluation": 0.0
    }
   }
  }
 },
 "domainCoverage": {
  "status": "ok",
  "treeVersion": "taxonomy-1013-pending",
  "definitions": "见 configs/profile.json domain.coverageDefinitions",
  "coverage": {
   "level1": 0.8125,
   "level2": 0.489362,
   "leaf": 0.244019,
   "labeledRecordRate": 0.896714
  },
  "labeledRecords": 382,
  "textRecords": 426,
  "level1": {
   "total": 16,
   "covered": 13,
   "counts": {
    "信息技术": 339,
    "生命科学": 62,
    "经济与金融": 28,
    "地球与环境": 18,
    "人文与学术": 13,
    "法律与安全": 12,
    "教育": 9,
    "传媒与文娱": 8,
    "商贸与消费": 7,
    "医疗健康": 3,
    "通信与物流": 3,
    "政务与公共管理": 2,
    "能源与电力": 2
   },
   "missing": [
    "工业制造",
    "建筑与地产",
    "农林牧渔与水利"
   ]
  },
  "level2": {
   "total": 47,
   "covered": 23,
   "counts": {
    "信息技术/语言智能": 334,
    "生命科学/生物": 53,
    "经济与金融/量化交易": 28,
    "地球与环境/遥感": 14,
    "人文与学术/人文社科": 13,
    "教育/教学与培训": 9,
    "生命科学/植物": 9,
    "法律与安全/军事": 7,
    "商贸与消费/营销与广告": 6,
    "信息技术/数字技术": 5,
    "传媒与文娱/社交媒体": 4,
    "法律与安全/法律法务": 4,
    "地球与环境/地理": 3,
    "通信与物流/交通出行": 3,
    "传媒与文娱/影视娱乐": 2,
    "传媒与文娱/游戏": 2,
    "医疗健康/医疗与医药": 2,
    "政务与公共管理/公共管理": 2,
    "能源与电力/能源": 2,
    "医疗健康/公共卫生": 1,
    "商贸与消费/餐饮": 1,
    "地球与环境/环境": 1,
    "法律与安全/安防与公共安全": 1
   },
   "missing": [
    "经济与金融/经济",
    "经济与金融/金融科技",
    "经济与金融/证券投资",
    "商贸与消费/商业运营",
    "商贸与消费/电商",
    "商贸与消费/旅游服务",
    "工业制造/制造业",
    "建筑与地产/建筑",
    "建筑与地产/房地产",
    "能源与电力/电力",
    "通信与物流/通信",
    "通信与物流/运输物流",
    "地球与环境/气象",
    "地球与环境/地质",
    "地球与环境/海洋",
    "传媒与文娱/新闻传媒",
    "传媒与文娱/体育运动",
    "教育/考试与评价",
    "农林牧渔与水利/农业",
    "农林牧渔与水利/林业",
    "农林牧渔与水利/畜牧业",
    "农林牧渔与水利/渔业",
    "农林牧渔与水利/水利",
    "政务与公共管理/政务"
   ]
  },
  "leaves": {
   "total": 209,
   "covered": 51,
   "top": [
    {
     "path": "信息技术/语言智能/机器翻译",
     "count": 118
    },
    {
     "path": "信息技术/语言智能/语义理解",
     "count": 113
    },
    {
     "path": "信息技术/语言智能/自然语言处理",
     "count": 80
    },
    {
     "path": "生命科学/生物/生物信息学",
     "count": 30
    },
    {
     "path": "信息技术/语言智能/多语言处理",
     "count": 23
    },
    {
     "path": "经济与金融/量化交易/因子研究",
     "count": 11
    },
    {
     "path": "经济与金融/量化交易/算法交易",
     "count": 11
    },
    {
     "path": "地球与环境/遥感/遥感图像处理",
     "count": 10
    },
    {
     "path": "生命科学/生物/分子生物学",
     "count": 10
    },
    {
     "path": "人文与学术/人文社科/历史学",
     "count": 7
    },
    {
     "path": "生命科学/生物/生物制药",
     "count": 7
    },
    {
     "path": "商贸与消费/营销与广告/用户触达",
     "count": 6
    },
    {
     "path": "生命科学/生物/细胞生物学",
     "count": 6
    },
    {
     "path": "经济与金融/量化交易/高频交易",
     "count": 6
    },
    {
     "path": "教育/教学与培训/高等教育",
     "count": 5
    },
    {
     "path": "教育/教学与培训/在线教育",
     "count": 4
    },
    {
     "path": "法律与安全/军事/军事训练",
     "count": 4
    },
    {
     "path": "法律与安全/法律法务/法律文书",
     "count": 4
    },
    {
     "path": "生命科学/植物/植物学",
     "count": 4
    },
    {
     "path": "生命科学/植物/植物育种",
     "count": 4
    },
    {
     "path": "人文与学术/人文社科/社会学",
     "count": 3
    },
    {
     "path": "传媒与文娱/社交媒体/内容推荐",
     "count": 3
    },
    {
     "path": "人文与学术/人文社科/哲学",
     "count": 2
    },
    {
     "path": "传媒与文娱/游戏/游戏数据分析",
     "count": 2
    },
    {
     "path": "地球与环境/地理/空间分析",
     "count": 2
    },
    {
     "path": "地球与环境/遥感/灾害遥感",
     "count": 2
    },
    {
     "path": "地球与环境/遥感/航空遥感",
     "count": 2
    },
    {
     "path": "法律与安全/军事/国防科技",
     "count": 2
    },
    {
     "path": "能源与电力/能源/能源节约",
     "count": 2
    },
    {
     "path": "通信与物流/交通出行/共享单车",
     "count": 2
    },
    {
     "path": "人文与学术/人文社科/文学",
     "count": 1
    },
    {
     "path": "传媒与文娱/影视娱乐/电影",
     "count": 1
    },
    {
     "path": "传媒与文娱/影视娱乐/短视频",
     "count": 1
    },
    {
     "path": "传媒与文娱/社交媒体/用户行为分析",
     "count": 1
    },
    {
     "path": "信息技术/数字技术/人工智能",
     "count": 1
    },
    {
     "path": "信息技术/数字技术/区块链",
     "count": 1
    },
    {
     "path": "信息技术/数字技术/大数据",
     "count": 1
    },
    {
     "path": "信息技术/数字技术/网络安全",
     "count": 1
    },
    {
     "path": "信息技术/数字技术/边缘计算",
     "count": 1
    },
    {
     "path": "医疗健康/公共卫生/流行病学调查",
     "count": 1
    },
    {
     "path": "医疗健康/医疗与医药/临床医学",
     "count": 1
    },
    {
     "path": "医疗健康/医疗与医药/生物医药",
     "count": 1
    },
    {
     "path": "商贸与消费/餐饮/正餐与快餐",
     "count": 1
    },
    {
     "path": "地球与环境/地理/地理信息系统",
     "count": 1
    },
    {
     "path": "地球与环境/环境/环境评估",
     "count": 1
    },
    {
     "path": "政务与公共管理/公共管理/公共服务",
     "count": 1
    },
    {
     "path": "政务与公共管理/公共管理/社会组织",
     "count": 1
    },
    {
     "path": "法律与安全/军事/情报分析",
     "count": 1
    },
    {
     "path": "法律与安全/安防与公共安全/智能安防",
     "count": 1
    },
    {
     "path": "生命科学/植物/药用植物",
     "count": 1
    }
   ]
  },
  "gaps": {
   "level1": [
    "工业制造",
    "建筑与地产",
    "农林牧渔与水利"
   ],
   "level2Count": 24
  }
 },
 "failedCount": 0,
 "failuresByReason": {},
 "treeVersion": "taxonomy-1013-pending",
 "provisional": true,
 "deterministic": true,
 "runtimeSec": 0.032,
 "generatedAt": "2026-11-17T10:53:31+08:00"
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

