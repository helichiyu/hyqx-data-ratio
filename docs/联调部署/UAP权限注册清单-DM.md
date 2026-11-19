# DM UAP 菜单与权限注册清单

> 版本：v1.0 / 2026-11-18
> 用途：在测试/生产环境 UAP 创建数据配比菜单、权限资源并完成角色授权。
> 配套：`hsmty-module-dm-server/tools/uap/import_dm.py`（dry-run/execute）、`check_permissions.py`（三处一致性检查）。

---

## 0. 先确认

| 项 | 说明 |
| --- | --- |
| 父菜单 | `YD数据平台`（脚本按名称解析，UUID 以实际环境为准） |
| 应用 | `AI云平台`（appId/appName 可用参数覆盖） |
| 前端路由前缀 | `/sdom-hsmty/#/data-mixing/...` |
| 页面 component key | `/data-mixing/{page}/index` |
| 权限码前缀 | `data-mixing:*` |
| 角色 | 测试账号所属角色（如 `test001`，可用 `--role-id` 或 `--role-name` 指定） |

> 不要直接复制其它环境/模块的 UUID；父菜单、应用、角色均由脚本按名称解析，或通过参数覆盖。

---

## 1. 菜单（3 个分组 + 10 个页面）

> 左侧菜单按原型拆成「数据治理」「配比生产」两个大菜单；原型中的「质量与合规」保留为第三组，
> 承载风险预警；专家校验已按 Comic 任务书删除，不再注册菜单。

| # | 名称 | 层级 | 上级 | URL | 排序 | 图标建议 |
| --- | --- | ---: | --- | --- | ---: | --- |
| 1 | 数据治理 | 4 | `YD数据平台` | — | 20 | `Collection` |
| 2 | 数据接入与标准化 | 5 | 数据治理 | `/sdom-hsmty/#/data-mixing/dataset/index` | 1 | — |
| 3 | 分类体系管理 | 5 | 数据治理 | `/sdom-hsmty/#/data-mixing/taxonomy/index` | 2 | — |
| 4 | 数据打标 | 5 | 数据治理 | `/sdom-hsmty/#/data-mixing/labeling/index` | 3 | — |
| 5 | 语料画像分析 | 5 | 数据治理 | `/sdom-hsmty/#/data-mixing/profile/index` | 4 | — |
| 6 | 配比生产 | 4 | `YD数据平台` | — | 21 | `Operation` |
| 7 | 场景管理 | 5 | 配比生产 | `/sdom-hsmty/#/data-mixing/scene/index` | 1 | — |
| 8 | 配比方案设计 | 5 | 配比生产 | `/sdom-hsmty/#/data-mixing/ratio-plan/index` | 2 | — |
| 9 | 配方包管理 | 5 | 配比生产 | `/sdom-hsmty/#/data-mixing/recipe/index` | 3 | — |
| 10 | 配比生产任务 | 5 | 配比生产 | `/sdom-hsmty/#/data-mixing/production/index` | 4 | — |
| 11 | 配比分析任务 | 5 | 配比生产 | `/sdom-hsmty/#/data-mixing/analysis/index` | 5 | — |
| 12 | 质量与合规 | 4 | `YD数据平台` | — | 22 | `Warning` |
| 13 | 风险预警 | 5 | 质量与合规 | `/sdom-hsmty/#/data-mixing/risk/index` | 1 | — |

`component` 必须与前端 `src/modules/data-mixing/register.ts` 的 key 一致：

```text
/data-mixing/dataset/index
/data-mixing/taxonomy/index
/data-mixing/labeling/index
/data-mixing/profile/index
/data-mixing/scene/index
/data-mixing/ratio-plan/index
/data-mixing/recipe/index
/data-mixing/production/index
/data-mixing/analysis/index
/data-mixing/risk/index
```

> 七维仿真与准入无独立菜单，入口在「配方包管理」页内，其权限资源关联到该菜单。

---

## 2. 权限资源（83 条）

`operation` 约定：

| operation | 含义 |
| ---: | --- |
| 0 | 新增 / 上传 / 生成（版本、报告、复制） |
| 1 | 修改 / 启停 / 启动 / 停止 / 发布 / 封存 / 回滚 / 校验 / 推荐 / 判定 / 处置 |
| 2 | 查询 / 详情 / 下拉 |
| 3 | 删除 |

### 2.1 数据接入与标准化

关联菜单：数据接入与标准化

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 数据接入与标准化-列表/选项 | `data-mixing:dataset:page` | 2 |
| 数据接入与标准化-详情/文件/下载/统计 | `data-mixing:dataset:detail` | 2 |
| 数据接入与标准化-新增 | `data-mixing:dataset:create` | 0 |
| 数据接入与标准化-修改 | `data-mixing:dataset:update` | 1 |
| 数据接入与标准化-启停 | `data-mixing:dataset:status` | 1 |
| 数据接入与标准化-删除 | `data-mixing:dataset:remove` | 3 |
| 数据接入与标准化-上传文件 | `data-mixing:dataset:upload` | 0 |

### 2.2 分类体系管理

关联菜单：分类体系管理

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 分类体系管理-树/选项/版本列表 | `data-mixing:taxonomy:page` | 2 |
| 分类体系管理-详情与查询 | `data-mixing:taxonomy:detail` | 2 |
| 分类体系管理-新增 | `data-mixing:taxonomy:create` | 0 |
| 分类体系管理-修改 | `data-mixing:taxonomy:update` | 1 |
| 分类体系管理-删除 | `data-mixing:taxonomy:remove` | 3 |
| 分类体系管理-启停 | `data-mixing:taxonomy:status` | 1 |
| 分类体系管理-排序 | `data-mixing:taxonomy:sort` | 1 |
| 分类体系管理-版本创建/切换/差异 | `data-mixing:taxonomy:version` | 0 |

### 2.3 数据打标

关联菜单：数据打标

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 数据打标-列表/选项 | `data-mixing:labeling:page` | 2 |
| 数据打标-详情/进度/样本/统计 | `data-mixing:labeling:detail` | 2 |
| 数据打标-新增 | `data-mixing:labeling:create` | 0 |
| 数据打标-启动/重跑 | `data-mixing:labeling:start` | 1 |
| 数据打标-停止 | `data-mixing:labeling:stop` | 1 |
| 数据打标-重跑 | `data-mixing:labeling:retry` | 1 |
| 数据打标-删除 | `data-mixing:labeling:remove` | 3 |
| 数据打标-人工复核 | `data-mixing:labeling:review` | 1 |

### 2.4 语料画像分析

关联菜单：语料画像分析

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 语料画像分析-列表/选项 | `data-mixing:profile:page` | 2 |
| 语料画像分析-概览/详情/进度/结果 | `data-mixing:profile:detail` | 2 |
| 语料画像分析-新增 | `data-mixing:profile:create` | 0 |
| 语料画像分析-启动/重跑 | `data-mixing:profile:start` | 1 |
| 语料画像分析-停止 | `data-mixing:profile:stop` | 1 |
| 语料画像分析-重跑 | `data-mixing:profile:retry` | 1 |
| 语料画像分析-删除 | `data-mixing:profile:remove` | 3 |

### 2.5 场景管理

关联菜单：场景管理

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 场景管理-列表/选项 | `data-mixing:scene:page` | 2 |
| 场景管理-详情与查询 | `data-mixing:scene:detail` | 2 |
| 场景管理-新增 | `data-mixing:scene:create` | 0 |
| 场景管理-修改 | `data-mixing:scene:update` | 1 |
| 场景管理-启停 | `data-mixing:scene:status` | 1 |
| 场景管理-删除 | `data-mixing:scene:remove` | 3 |

### 2.6 配比方案设计

关联菜单：配比方案设计

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 配比方案设计-列表/选项 | `data-mixing:ratio-plan:page` | 2 |
| 配比方案设计-详情/推荐记录 | `data-mixing:ratio-plan:detail` | 2 |
| 配比方案设计-新增 | `data-mixing:ratio-plan:create` | 0 |
| 配比方案设计-修改 | `data-mixing:ratio-plan:update` | 1 |
| 配比方案设计-启停 | `data-mixing:ratio-plan:status` | 1 |
| 配比方案设计-删除 | `data-mixing:ratio-plan:remove` | 3 |
| 配比方案设计-复制 | `data-mixing:ratio-plan:copy` | 0 |
| 配比方案设计-校验 | `data-mixing:ratio-plan:validate` | 1 |
| 配比方案设计-生成推荐/标记应用 | `data-mixing:ratio-plan:recommend` | 1 |

### 2.7 配方包管理

关联菜单：配方包管理

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 配方包管理-列表/选项 | `data-mixing:recipe:page` | 2 |
| 配方包管理-详情/版本/差异 | `data-mixing:recipe:detail` | 2 |
| 配方包管理-新增 | `data-mixing:recipe:create` | 0 |
| 配方包管理-修改 | `data-mixing:recipe:update` | 1 |
| 配方包管理-删除 | `data-mixing:recipe:remove` | 3 |
| 配方包管理-生成版本 | `data-mixing:recipe:version` | 0 |
| 配方包管理-发布 | `data-mixing:recipe:publish` | 1 |
| 配方包管理-封存 | `data-mixing:recipe:seal` | 1 |
| 配方包管理-回滚 | `data-mixing:recipe:rollback` | 1 |

### 2.8 七维仿真与准入

关联菜单：配方包管理

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 七维仿真与准入-列表/选项 | `data-mixing:simulation:page` | 2 |
| 七维仿真与准入-详情/进度/结果/判定 | `data-mixing:simulation:detail` | 2 |
| 七维仿真与准入-新增 | `data-mixing:simulation:create` | 0 |
| 七维仿真与准入-启动/重跑 | `data-mixing:simulation:start` | 1 |
| 七维仿真与准入-停止 | `data-mixing:simulation:stop` | 1 |
| 七维仿真与准入-重跑 | `data-mixing:simulation:retry` | 1 |
| 七维仿真与准入-删除 | `data-mixing:simulation:remove` | 3 |
| 七维仿真与准入-准入判定 | `data-mixing:simulation:decide` | 1 |

### 2.9 配比生产任务

关联菜单：配比生产任务

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 配比生产任务-列表/选项 | `data-mixing:production:page` | 2 |
| 配比生产任务-详情/执行/产物/算子/文件 | `data-mixing:production:detail` | 2 |
| 配比生产任务-新增 | `data-mixing:production:create` | 0 |
| 配比生产任务-启动/重跑 | `data-mixing:production:start` | 1 |
| 配比生产任务-停止 | `data-mixing:production:stop` | 1 |
| 配比生产任务-重跑 | `data-mixing:production:retry` | 1 |
| 配比生产任务-删除 | `data-mixing:production:remove` | 3 |

### 2.10 配比分析任务

关联菜单：配比分析任务

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 配比分析任务-列表/选项 | `data-mixing:analysis:page` | 2 |
| 配比分析任务-详情/结果/报告/下载 | `data-mixing:analysis:detail` | 2 |
| 配比分析任务-新增 | `data-mixing:analysis:create` | 0 |
| 配比分析任务-启动/重跑 | `data-mixing:analysis:start` | 1 |
| 配比分析任务-停止 | `data-mixing:analysis:stop` | 1 |
| 配比分析任务-重跑 | `data-mixing:analysis:retry` | 1 |
| 配比分析任务-删除 | `data-mixing:analysis:remove` | 3 |
| 配比分析任务-生成报告 | `data-mixing:analysis:report` | 0 |

### 2.11 风险预警

关联菜单：风险预警

| 资源名称 | 权限码 | operation |
| --- | --- | ---: |
| 风险预警-列表/统计 | `data-mixing:risk:page` | 2 |
| 风险预警-详情与查询 | `data-mixing:risk:detail` | 2 |
| 风险预警-新增 | `data-mixing:risk:create` | 0 |
| 风险预警-修改 | `data-mixing:risk:update` | 1 |
| 风险预警-删除 | `data-mixing:risk:remove` | 3 |
| 风险预警-风险处置 | `data-mixing:risk:handle` | 1 |

---

## 3. 角色授权与验收

1. 先 dry-run 核对将创建/复用的菜单与资源：
   ```bash
   python tools/uap/import_dm.py --curl-file uap.curl
   ```
2. 确认后执行：
   ```bash
   python tools/uap/import_dm.py --curl-file uap.curl --role-name test001 --execute
   ```
3. 重新登录平台，确认：
   - `permissions/verify` 返回包含 `data-mixing:*`；
   - `auth/selectedTree?roleId=...` 勾选「数据治理」「配比生产」「质量与合规」及各自页面；
   - 侧边菜单可见，页面无白屏。
4. 任一步失败时，脚本会打印 HTTP 状态与响应体（不含 Cookie），按响应修正后重跑；重复执行按名称复用，不会重复创建。

## 4. 注意事项

- Cookie 只通过 `UAP_COOKIE` 环境变量或 `--curl-file` 读取，禁止写入仓库、日志和命令历史。
- 菜单授权 `role/disAuth` 会覆盖角色菜单集合；脚本会先读取 `auth/selectedTree` 的已选菜单并合并，避免丢失其它模块菜单。
- `resourceIds` / `authIds` 使用**单个逗号分隔字符串**；如目标环境只接受重复字段，可加 `--repeat-fields`。
- 资源 `code` 与 `value` 都必须等于权限码，`operation` 为数字字符串。
- 菜单按「父级 + 名称」复用；重复执行不会重复创建。
