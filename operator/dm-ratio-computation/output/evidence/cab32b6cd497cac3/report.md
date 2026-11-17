# 工作包回执 · OP-15（配比引擎）

## 状态
完成（本机真实链路）；S4 阶段结果见阶段索引，效果与阈值待人工确认（H-03/Q-04）。

## 运行命令
```bash
"D:/anaconda3/envs/use/python.exe" scripts/run_s4_chain.py
```

## 证据路径
- 结果目录：`E:/HYQX/数据配比/operator/runtime/transport/output/dm-ratio-computation/cab32b6cd497cac3`
- 方案表：`result.jsonl` / `plan.json`
- 校验单：`validation.json`
- 指标：`metrics.json`

## 指标
| 项 | 值 |
| --- | --- |
| 标签数 | 66 |
| 有效条数合计 | 278.0 |
| 占比合计 | 1.0（误差 0.0） |
| 目标投喂 | 100000（实际 100000） |
| 检查通过 | 3/6 |
| 库存缺口 | 99722 |

校验单：

| 检查 | 实测 | 阈值 | 结果 | 来源 |
| --- | --- | --- | --- | --- |
| sum_100 | 1.0 | 1.0 | 通过 | 任务书 S4 门禁 / baseline ratio.sum_target |
| core_label_coverage | 0.5608 | 0.3 | 通过 | baseline coverage.core_label_min（H-03） |
| level1_coverage | 0.733333 | 1.0 | 未通过 | baseline coverage.level1_min（H-03） |
| level2_coverage | 0.377193 | 1.0 | 未通过 | baseline coverage.level2_min（H-03） |
| min_sample | 100000 | 100000 | 通过 | baseline sample.min_total（H-03） |
| inventory_gap | 99722 | 0 | 未通过 | 任务书 S4 门禁：库存折算 |

## 未决问题
- 一级/二级覆盖与库存缺口在小批次必然不达标：如实记录，未调整阈值凑通过。
- 权重链路系数默认 1.0（Q-04 未提供），结果标 `provisional`。
- 0.1.1 追加 `bySource`（只增不改），供 OP-16 能力映射与补数来源。
