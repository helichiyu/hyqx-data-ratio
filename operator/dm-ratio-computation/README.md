# OP-15 配比引擎（`dm-ratio-computation`）

- 语义编码：`ratio_weighted_plan_v1`
- 阶段/优先级：S4 / P0
- 版本：`0.1.2`（0.1.1 追加 `bySource`；0.1.2 让 manifest.runId 与 HTTP 运行目录名同口径）
- 模型：无

## 1. 用途与边界

**做**：由 OP-05 标签构建标签×来源库存；按权重链路计算有效条数与占比；最大余数法归一化；输出三列方案表、投喂条数、校验单、未覆盖类别与缺口。

**不做**：不写数据库/配方包状态机；不提供 UI；不替业务确认权重。

## 2. 权重链路（写入 README，可按条数复算）

```text
有效条数(label) = Σ_source 条数(label, source)
                  × 来源权重(source)
                  × 偏见降权(source)
                  × 角色系数(source)
                  × 阶段系数(source)
                  × 标签权重(label)

占比(label) = 有效条数 / Σ 全部有效条数
投喂条数(label) = round(占比(label) × 目标总量)
```

- 全部系数默认 1.0（Q-04 未提供），结果标 `provisional`；
- 归一化：最大余数法，单位 `10^-4`（0.01%），长尾至少 1 个单位，不置零；
- 校验单：`sum_100`、`core_label_coverage`、`level1_coverage`、`level2_coverage`、`min_sample`、`inventory_gap`，每项带实测值、阈值与来源；
- 0.1.1 起每行附带 `bySource`（`{来源: {count, effectiveCount}}`），供 OP-16 能力映射与补数来源推荐使用。

## 3. 接口与参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `labels_path` | 无 | OP-05 结果目录/文件，须在 `INPUT_DIR`/`OUTPUT_DIR` 内 |
| `target_total` | 100000 | 目标投喂总量 |
| `label_weights` | 无 | 标签权重覆盖（`{labelPath: weight}`） |

## 4. 复算与测试

```bash
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-ratio-computation/tests
```

## 5. 已知限制

1. token 用文本字符数近似（平台提供真实 token 后可替换）；
2. 角色/阶段系数、来源权重、偏见降权、核心标签口径待业务确认（Q-04/H-03）；
3. 一级/二级覆盖按内容树全集检查，小批次必然不达标，如实记录；
4. 不自动调整阈值凑通过。

## 6. 版本与证据

`operatorVersion=0.1.2`、`modelVersion=null`、`treeVersion=taxonomy-1013-pending`；
证据目录 `operator/dm-ratio-computation/output/evidence/<runId>/`。
