# 工作包回执 · OP-21（专家校验）

## 状态
完成（本机真实链路）；S6 阶段资源/阈值待人工确认（H-03/H-05/H-11/Q-07）。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s6_chain.py
```

## 证据路径
- 结果目录：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-expert-validation/8ea8159784975ebe`

## 指标
| 项 | 值 |
| --- | --- |
| 总体 / 实抽 | 278 / 28 |
| 实抽比例 | 0.100719 |
| 高风险补入 | 0 |
| 一致性状态 | blocked |
| Kappa / Alpha | None / None |

## 未决问题
- 本体/KG/词表（H-11）、专家标注（H-05）、风险阈值（H-03）、Neo4j/FAISS（Q-07）待人工。
- 资源缺失项标 unavailable/blocked，不编造。
