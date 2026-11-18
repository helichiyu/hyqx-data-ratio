# 工作包回执 · OP-19（配比分析与报告）

## 状态
完成（本机真实链路）；S5 阶段效果与阈值待人工确认（H-03/H-05/Q-08）。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s5_chain.py
```

## 证据路径
- 结果目录：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-ratio-reporting/97ed001cc0ab02da`
- 指标：`metrics.json`

## 指标
| 项 | 值 |
| --- | --- |
| 综合评分 / 等级 | 0.6889305599 / pass |
| 可用维度 / 总维度 | 9 / 9 |
| 缺失维度 | 无 |
| 渲染状态 | ok |

## 未决问题
- 真值/合规词表/版权库缺失时效果指标为 null/unavailable，不编造（H-05/Q-08）。
- 小批次库存不足导致实抽远低于 10 万配额，如实记录。
