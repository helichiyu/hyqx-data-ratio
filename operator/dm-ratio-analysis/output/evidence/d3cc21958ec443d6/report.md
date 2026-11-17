# 工作包回执 · OP-16（配比分析与建议）

## 状态
完成（本机真实链路）；S4 阶段 P1 能力完成，映射库/目标能力/阈值待人工确认（Q-05/H-12/H-03）。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s4_chain.py
```

## 证据路径
- 结果目录：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-ratio-analysis/d3cc21958ec443d6`
- 能力分/贡献度：`capability.json`
- 建议配比与约束单：`recommendation.json`
- 补数建议：`topup.json`
- 多方案对标：`benchmark.json`
- 指标：`metrics.json`

## 指标
| 项 | 值 |
| --- | --- |
| 标签数 | 66 |
| 能力分（当前，六维合计） | 1.0 |
| 能力分（建议，六维合计） | 1.0 |
| 目标模板 | balanced（config:profile:balanced） |
| 达成度 当前→建议 | 0.7413773333 → 0.7629384951（增益 0.0215611618） |
| 约束通过 | True（迭代 19，收敛 True） |
| 改动量 L1/2 | 0.107806（上限 0.5） |
| 库存缺口 / 缺口标签 | 99722 / 66 |
| 偏见等级（来源/领域） | high / high |
| 对标推荐方案 | balanced |

六维能力分（当前 → 建议，0–10）：

| 维度 | 当前 | 建议 |
| --- | --- | --- |
| language | 2.6007 | 2.385 |
| knowledge | 2.4477 | 2.3938 |
| reasoning | 2.5379 | 2.5918 |
| expertise | 1.2897 | 1.667 |
| coding | 0.3597 | 0.3058 |
| dialogue | 0.7644 | 0.6566 |

## 已通过的必做验证
- 能力贡献可加总：`tests/test_op16.py::test_capability_contributions_sum`。
- 建议满足约束且改动量可解释：约束单 3/3，改动 Top10 见 `recommendation.json`。
- 补数按真实库存：`topup.json` 缺口 = 建议投喂 − 真实库存。
- 达成度 = 目标 vs 实际：逐维 `actual/target/ratio/gap` 见 `capability.json`。
- 偏见/对标可复算：`tests/test_op16.py` 手工指标与对标对拍。
- 无硬编码 fit 向量：能力映射来自 FGW 12.1 可解释默认映射，逐来源权重写入 `analysis.json`。

## 未决问题
- 权威能力/领域映射库（Q-05）与目标能力模板（H-12）待人工确认；当前全部标 `provisional`。
- 六维能力分是配比结构的可解释刻画，不等价于模型评测分数。
- 小批次库存缺口大，补数建议引用真实库存，不推算不存在的数据。
