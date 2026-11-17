# 工作包回执 · OP-17（数据组装与打包）

## 状态
完成（本机真实链路）；S5 阶段效果与阈值待人工确认（H-03/H-05/Q-08）。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s5_chain.py
```

## 证据路径
- 结果目录：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-dataset-packaging/347d6365d8457c91`
- 指标：`metrics.json`

## 指标
| 项 | 值 |
| --- | --- |
| 选样数 / 配额 | 278 / 100000 |
| 库存缺口 | 99722 |
| Parquet 分片 / 行数 / 字节 | 7 / 278 / 173120 |
| 重复记录 | 0 |
| 层偏差最大值 / 来源偏差 | None / 6.3e-05 |

## 未决问题
- 真值/合规词表/版权库缺失时效果指标为 null/unavailable，不编造（H-05/Q-08）。
- 小批次库存不足导致实抽远低于 10 万配额，如实记录。
