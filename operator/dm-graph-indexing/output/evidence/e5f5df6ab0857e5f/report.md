# 工作包回执 · OP-20（知识图谱与向量索引）

## 状态
完成（本机真实链路）；S6 阶段资源/阈值待人工确认（H-03/H-05/H-11/Q-07）。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s6_chain.py
```

## 证据路径
- 结果目录：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-graph-indexing/e5f5df6ab0857e5f`

## 指标
| 项 | 值 |
| --- | --- |
| 节点 / 边 | 1309 / 6232 |
| 实体数 | 746 |
| 向量数 / 维度 | 426 / 768 |
| recall@10 / QPS | 0.875 / 6666.62 |
| Neo4j / FAISS | unavailable / unavailable |

## 未决问题
- 本体/KG/词表（H-11）、专家标注（H-05）、风险阈值（H-03）、Neo4j/FAISS（Q-07）待人工。
- 资源缺失项标 unavailable/blocked，不编造。
