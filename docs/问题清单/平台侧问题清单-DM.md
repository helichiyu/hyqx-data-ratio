# DM 平台侧问题清单（内部跟踪，勿混入算法问题）

> 记录日期：2026-11-19
> 说明：打标缺权重、语音依赖、OP-06/OP-08 等属于算法侧，见 `算法侧问题清单-DM.md`。
> 本文件只记录**平台编排/功能**的完成情况，不要发给算法同事。

---

## 1. 七维仿真执行链（已实现并验证）

**原现象**：仿真任务直接 failed，提示“尚未编排执行链”。

**已做**：

- `SimulationServiceImpl` 从配方包版本快照构建 `plan.json`（目标比例 / 目标总量 / feedCount）；
- 上传 plan 到算子池，调用 OP-16（`dm-ratio-analysis`）；
- 结果写 `seven_dim_json`，记录 `algorithm_output_dir`，任务 completed。

**验证**：用「联调-配方A v1」发起仿真，任务 completed，结果包含
`capability / achievement / recommendation / bias / domain / topUp / benchmark`。

**剩余**：仿真分数目前依赖配方快照中的比例与库存；缺少 OP-05 标签时
`achievement` 可能为 0，结果仍会如实返回，不伪造。

---

## 2. 配比生产执行链（已实现，待打标权重到位后端到端验证）

**原现象**：生产任务直接 failed。

**已做**：

- `production_task` 增加 `dataset_id / labeling_task_id / plan_output_dir / algorithm_output_dir`；
- 新建生产任务必须选择数据集；
- 生产时查找该数据集最近一次已完成打标任务，复用其 OP-02 records 与 OP-05 labels；
- 从配方版本快照生成 `plan.json`，上传算子池，调用 OP-17（`dm-dataset-packaging`）；
- 成品目录下载为 zip 存本地存储，写 `stage_artifact`、`operator_run`、`operator_stat`；
- 库存不足时按 `allowShortage` 标记 completed / partial_failed，写缺口说明。

**当前阻塞**：本地 git checkout 不带权重，本次 `operator/weights/` 为空，打标无法完成，因此生产会明确失败：

```text
请先完成数据集【...】的数据打标并产出样本
```

**待验证**：按发布包/模型仓准备权重、打标 completed 后，用同一数据集发起生产，确认成品 zip、
阶段产物、算子运行记录与缺口统计。

---

## 3. 配比分析执行链（已实现，待生产产物）

**原现象**：分析任务直接 failed，无结果、报告按钮禁用。

**已做**：

- `analysis_task` 增加 `algorithm_output_dir`；
- `report` 类型：以 OP-17 产物目录 + 已完成的画像目录组成 `operator_results`，调用 OP-19
  （`dm-ratio-reporting`），结果写入 `analysis_result`；
- `nine_dim/ratio` 类型：复用生产任务的 `plan_output_dir` 调用 OP-16；
- 有结果后「生成报告」可用（HTML/Excel）；PDF 仍未实现。

**当前阻塞**：生产未成功，分析会明确失败：

```text
请先完成配比生产任务（生产任务需绑定数据集并成功产出成品）
```

**待验证**：生产/画像产物齐全后，确认九维结果与 HTML/Excel 报告。

---

## 4. 版本差异 changedCount（已实现）

**已做**：`TaxonomyServiceImpl.versionDiff()` 现在按路径比较 nodeName/modal/status/description，
同一路径属性变化计入 `changedCount/changedPaths`；新增/删除仍分别统计。

**注意**：节点改名会同时表现为“删旧路径 + 加新路径”，这是路径级差异的固有结果。

---

## 5. 版本删除/清理（已实现）

**已做**：分类版本列表对非生效版本提供「删除」，后端同时逻辑删除版本及其节点快照；
生效版本拒绝删除。已验证：创建草稿 → 新增根节点 → 删除草稿成功；对生效版本新增节点返回
「只有草稿版本可以编辑」。


## 7. 画像风险生成与数据集级报告（已实现）

- 风险页新增「从画像生成风险」：根据已完成 quality/basic/language/text 画像生成质量、偏见、时效风险；
  同数据集同标题的未关闭风险不重复生成；实测可从现有画像生成 2 条风险。
- 配比分析「报告」类型在没有生产任务时，可用已完成画像 metrics 生成数据集级 OP-19 报告；
  「九维/比例」仍要求成功生产任务（需要 plan 产物）。

---

## 6. 当前结论（2026-11-19 Comic 范围）

- 算子收敛为 14 个（OP-01/02/05/06/08/09/10/11/12/13/14/16/17/19）；专家校验、OP-18 评测、OP-21/22 已下线；
- 仿真：已修复并验证；
- 生产/分析：平台编排已实现，前端有数据集选择，失败信息能指向上游缺失；
- basic 画像已接 OP-06，分类树按任务上传快照；生效/归档版本只读，UI 已增加只读提示与草稿版本编辑引导；
- 端到端成功验证依赖算法侧权重（打标）与已完成打标；本机 git checkout 不带权重，需从发布包/模型仓准备；
- 版本删除/清理已实现（仅非生效版本）；
- Comic 任务书中的准确率/F1/Kappa 等无真值指标不实现、不伪造，统一按过程指标与结果 JSON 展示；
- Comic 的智能推荐、参考配方复刻、数据集包深度分析等额外模块按 Q-12 默认范围外，本轮不实现；当前保证 5 类业务任务链与 10 个页面。
