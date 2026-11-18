# 工作包回执 · OP-18（数据评测）

## 状态
完成（本机真实链路）；S5 阶段效果与阈值待人工确认（H-03/H-05/Q-08）。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s5_chain.py
```

## 证据路径
- 结果目录：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-dataset-evaluation/58eca6093ec0227c`
- 指标：`metrics.json`

## 指标
| 项 | 值 |
| --- | --- |
| 抽样数 / 总体 | 31 / 278 |
| 真值状态 | unavailable |
| 准确率 / 宏 F1 | None / None |
| 路径合法率 | 1.0 |
| 合规状态 | ok |
| 综合质量分 | 1.0（proxy_excellent） |

## 未决问题
- 真值/合规词表/版权库缺失时效果指标为 null/unavailable，不编造（H-05/Q-08）。
- 小批次库存不足导致实抽远低于 10 万配额，如实记录。
