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

**当前阻塞**：本机没有 bge 权重，打标无法完成，因此生产会明确失败：

```text
请先完成数据集【...】的数据打标并产出样本
```

**待验证**：权重到位、打标 completed 后，用同一数据集发起生产，确认成品 zip、
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

## 4. 版本差异仅统计新增/删除（P2，未改）

**现象**：`changedCount` 始终为 0；节点改名表现为“删旧路径 + 加新路径”。

**原因**：`TaxonomyServiceImpl.versionDiff()` 只比较 `node_path` 集合。

**待补**：按路径比较 nodeName/modal/status，填充 changedPaths。

---

## 5. 版本删除/清理缺失（P2，未改）

**现象**：性能验证创建了多个草稿版本，页面无法删除。

**待补**：仅允许删除非生效、未被业务引用的版本。

---

## 6. 当前结论

- 仿真：**已修复并验证**；
- 生产/分析：**平台编排已实现**，前端有数据集选择，失败信息能指向上游缺失；
- 端到端成功验证依赖算法侧 bge 权重（打标）与画像产物；
- 版本差异/删除属于 P2 收尾，不影响主流程。
