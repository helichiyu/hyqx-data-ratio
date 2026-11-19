# DM 平台开发记录（原 feature 分支 todo_1118_4.md）

# TODO: 数据配比（DM）第四批域：配方包 + 七维仿真/准入 - 2026-11-18

## 需求描述

1. **配方包（recipe）**：由配比方案生成不可变版本快照，支持草稿、发布、封存、回滚、版本差异。
2. **七维仿真与训练准入（simulation/admission）**：仿真任务生命周期、七维结果读取、准入判定与记录。

沿用已确认口径：表 `hs_data_mixing_*`、接口 `/hs-api/data-mixing`、权限 `data-mixing:*`、库 `idg_db`、算法只保留网关抽象。

## 任务清单

- [x] 1.1 PO/Mapper：Recipe、RecipeVersion、SimulationTask、AdmissionDecision
- [x] 1.2 配方包 CRUD、删除保护（生产任务引用）、方案/场景一致性校验
- [x] 1.3 版本快照：方案详情 + 场景详情 JSON；版本号递增；差异（新增/删除/比例变化/目标总量）
- [x] 1.4 版本生命周期：draft → published → sealed；回滚当前版本
- [x] 1.5 Liquibase 012：`recipe_code` 允许为空（前缀待平台分配）
- [x] 1.6 仿真任务 CRUD/启动/停止/重跑/进度；仅已发布/已封存版本可仿真
- [x] 1.7 仿真结果读取；准入判定 pass/reject/pending、综合得分、维度 JSON、判定人/时间
- [x] 1.8 Controller + 权限码 `data-mixing:recipe:*`、`data-mixing:simulation:*`
- [x] 1.9 构建、Liquibase 012、local-dev 冒烟、测试数据清理

## 验收结果

1. 配方包创建（绑定已启用方案/场景）成功；版本 v1 生成快照，发布后 recipe.currentVersion=1、状态 published。
2. 版本 v2 生成成功，差异为 0；封存 v2 成功；回滚后 currentVersion=2。
3. 配方包 options 返回已发布配方（当前版本 2）。
4. 仿真任务以 sealed v2 创建并启动，约 1 秒失败，`errorCode=ALGORITHM_UNAVAILABLE`，错误信息可读。
5. 仿真未完成时 `pass` 判定返回 400「仿真未完成，无法判定」；`pending` 判定可记录。
6. 用测试数据将仿真置为 completed 且写入七维 JSON 后，`pass` 判定成功，自动取 `totalScore=87.5`，结果接口返回七维 JSON 与两条判定记录。
7. 清理后：配方包 0、版本 0、仿真 0、判定 0、方案 0、场景 0。

## 已知限制

- 配方包编号前缀未登记，`recipe_code` 暂为空（迁移已允许空值）。
- 七维仿真算法客户端未接入，`run()` 在健康检查后明确失败；接入时补 `submitSimulation` 与结果落库。
- 配方包版本差异按标签路径与比例比较，未比较质量阈值等行级字段。

## 下一步

1. 生产任务与执行链（production）：任务/执行记录/阶段产物/算子运行/统计/文件流转。
2. 配比分析（analysis）与分析报告（HTML/PDF/Excel）。
3. 风险预警（risk）与专家校验（expert）。

## 执行记录

### 2026-11-18 12:55–13:05

- 新增 22 条接口路径：配方包 10 条（含版本/发布/封存/回滚/差异）、仿真 10 条（含判定/结果）。
- Liquibase 012 执行成功。
- 首次冒烟发现 `recipe_code` 为 NOT NULL 导致插入失败，已通过 012 改为可空并复测通过。
- 冒烟脚本 `smoke7.py`、`smoke7b.py`；测试数据已物理清理。
