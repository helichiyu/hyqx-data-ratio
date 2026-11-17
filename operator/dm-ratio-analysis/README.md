# OP-16 配比分析与建议（`dm-ratio-analysis`）

- 语义编码：`ratio_analysis_recommend_v1`
- 阶段/优先级：S4 / P1
- 版本：`0.1.2`（0.1.1：目标改为目标亏空加权和；0.1.2：领域偏见覆盖全树、补数引用未覆盖清单、取整回退与预算预留）
- 模型：无（规则/优化，可解释映射 + 凸优化）

## 1. 用途与边界

**做**：

1. 六维能力分与逐标签贡献度（`capability.json`）；
2. 内容树一级/二级领域相对占比与未覆盖清单；
3. 目标能力下的建议配比、预期提升与改动量（`recommendation.json`）；
4. 按真实库存的补数 TopN、推荐补数来源与补齐后能力预测（`topup.json`）；
5. 来源/领域偏见指标（基尼、HHI、归一化熵、头部占比）；
6. 通用/专业多方案对标矩阵（`benchmark.json`）。

**不做**：不写数据库/配方包状态机；不做 UI；不替业务确认映射库、目标能力与阈值；
不编造人工标注/专家真值；不计算 OP-18 的评测准确率。

## 2. 能力映射口径（FGW 12.1，写入结果可复核）

### 2.1 六维能力

| key | 中文 | 依据（FGW 12.1） |
| --- | --- | --- |
| `language` | 语言理解与生成 | 网络文本提供广泛语言与多种文本风格；书籍提供正式语言风格 |
| `knowledge` | 知识广度 | 网络文本覆盖广泛主题；维基百科提供百科全书式事实知识 |
| `reasoning` | 推理能力 | 网络文本的常识推理、书籍的长距离依赖、科学文献的复杂推理 |
| `expertise` | 专业深度 | 书籍与科学文献提供技术知识与正式专业写作 |
| `coding` | 编码能力 | 代码库直接影响编码辅助能力 |
| `dialogue` | 对话交互 | 网络文本支撑通用会话；对话数据提供会话流程与轮流发言 |

来源→能力权重见 `configs/analysis.json` 的 `capability.sourceWeights`，每个来源一行、合计 1。
Q-05 权威「数据源-能力塑造知识库」未提供，本权重是**由 FGW 文字描述转成的可解释默认映射**，
不是模型 fit 向量；结果统一标 `provisional`，权威库到位后按版本替换。

### 2.2 能力分与贡献度

```text
标签来源构成(label, source) = 有效条数(label, source) / Σ_source 有效条数(label, source)
标签能力向量(label, dim)   = Σ_source 标签来源构成(label, source) × 来源能力权重(source, dim)
能力分(dim)                = Σ_label 方案占比(label) × 标签能力向量(label, dim)
贡献度(label, dim)         = 方案占比(label) × 标签能力向量(label, dim)
```

- 每个标签的能力向量合计 1，因此六维能力分合计 1；`score10 = 能力分 × 10`；
- 贡献度逐标签可加总回能力分（`capability.json` 的 `contributions`）。

## 3. 建议配比（目标函数与约束）

```text
minimize   Σ_dim objectiveWeights(dim) × max(0, target(dim) − achieved(dim))
subject to Σ_label share(label) = 1
           minLabelShare ≤ share(label) ≤ maxLabelShare
           0.5 × Σ_label |share(label) − current(label)| ≤ maxTotalChangeL1
```

目标只惩罚「未达目标的亏空」，与达成度 `Σ min(实际,目标)/Σ目标` 严格同向；
已超目标的维度不因超配而被压回，避免“目标函数下降但达成度也下降”。

- 目标能力模板（`configured profiles`）：`balanced`（六维等权）、`general`（通用/基座）、
  `professional`（行业/专业），来自 FGW 12.4-4 应用导向规则，标「联调初值」；
  也可通过 `params.target_capability` 直接传入六维目标（自动归一化）；
- 求解：Frank-Wolfe（条件梯度），每步在所有「仍有可减空间」的标签中选贡献最低者为供体、
  在「仍有可加空间」的标签中选贡献最高者为受体，沿方向做凸分段线性目标的精确三分搜索；
  全程确定、无随机数；
- 取整：最大余数法（默认 6 位小数），保证合计严格 100%、长尾不置零；
- 取整后若目标函数不比当前方案更优，回退到当前方案并记录 `reverted=true`，保证预期提升非负；
- 改动超上限时按 `current + α(optimized − current)` 收缩到 `maxTotalChangeL1`，并记录 `changeClipped`；
- 约束核对逐项输出实测值、阈值与来源（`sum_100`、`label_bounds`、`change_limit`）。

## 4. 达成度、补数与偏见

- **达成度**：`overall = Σ_dim min(实际, 目标) / Σ_dim 目标`（等价于 `1 − 0.5·L1`）；
  逐维输出 `actual/target/ratio/gap`。
- **补数**：`缺口 = round(建议占比 × 目标总量) − 真实库存`；
  按目标能力缺口方向与来源能力映射的匹配度排序推荐来源，补样量按匹配度分摊；
  补齐后能力按「现有库存 + 补数来源」重新加权；优先级按缺口/目标总量分级（≥1% 高、≥0.2% 中）；
  无可用来源映射的缺口计入 `sourceTotals.unknown`（需平台补采，不伪造来源）；
  各来源补样量用最大余数法取整，合计严格等于 `totalGap`；
  同时输出未覆盖的一级/二级领域清单（无库存，需平台补采）。
- **偏见**：对固定六类来源分布与内容树全部一级领域（含未覆盖类别的 0 占比）计算基尼、HHI、归一化熵；
  阈值见 `configs/analysis.json` 的 `bias`（基尼 0.6 沿用 baseline，HHI/熵为联调初值）。
- **对标**：`current`、`balanced`、`general`、`professional`（可选 `custom`）四/五个方案，
  逐方案给出六维能力、三套目标模板的达成度、来源/领域覆盖、通用占比、专业占比与改动量。

## 5. 接口与参数

`input_path` 为 OP-15 运行目录（含 `plan.json`，需 OP-15 ≥0.1.1 的 `bySource`）。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `plan_path` | 无 | 覆盖 OP-15 `plan.json`/`result.jsonl` 路径（须在 `INPUT_DIR`/`OUTPUT_DIR` 内） |
| `target_total` | 方案表目标总量 | 目标投喂总量（用于补数缺口） |
| `orientation` | `balanced` | `balanced` / `general` / `professional` |
| `target_capability` | 无 | 六维目标能力 `{dim: value}`，传入后 `orientation=custom` |

## 6. 运行与测试

```bash
# 单测（含真实批次）
"D:/anaconda3/envs/use/python.exe" -m pytest operator/dm-ratio-analysis/tests

# 本地样例
"D:/anaconda3/envs/use/python.exe" - <<'PY'
import os, sys; sys.path.insert(0, "operator")
os.environ.setdefault("INPUT_DIR", "operator")
import inference
core = inference._import_operator_core("dm-ratio-analysis")
print(core.run("operator/dm-ratio-analysis/dataset/sample/plan", {}, 42,
               "operator/runtime/output/op16-demo")["metrics"]["recommendation"])
PY
```

## 7. 指标口径与已知限制

| 指标 | 口径 | 备注 |
| --- | --- | --- |
| 能力分 | `Σ_label 占比 × 标签能力向量` | 合计 1，`score10` 为 0–10 展示分 |
| 达成度 | `Σ min(实际, 目标) / Σ 目标` | 逐维 ratio/gap 同时输出 |
| 改动量 | `0.5 × Σ|建议 − 当前|` | 上限 `maxTotalChangeL1` |
| 补数缺口 | `round(建议占比×目标总量) − 库存` | 只用真实库存，不推算 |
| 偏见 | 基尼 / HHI / 归一化熵 | 阈值为联调初值 |

1. 能力映射为 FGW 12.1 可解释默认映射，权威映射库（Q-05）与目标能力模板（H-12）待业务确认；
2. 能力分是「数据配比结构 → 能力倾向」的可解释刻画，不等价于模型真实能力评测；
3. 来源构成沿用 OP-15 库存，不重新抽样；补数后的能力预测假设补数来源按推荐比例落地；
4. 建议配比受总改动上限约束，超限时收缩并记录，不宣称全局最优；
5. 小批次（如 2 个标签）下建议可能被改动上限截断，结果如实记录。

## 8. 版本与证据

`operatorVersion=0.1.2`、`modelVersion=null`、`treeVersion=taxonomy-1013-pending`、
`mappingVersion=0.1.0`；证据目录 `operator/dm-ratio-analysis/output/evidence/<runId>/`。
