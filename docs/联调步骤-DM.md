# 数据配比（DM）联调步骤

> 版本：v1.0 / 2026-11-18
> 适用：后端 `hsmty-module-dm-server`、前端 `hsmty-web/src/modules/data-mixing`、UAP 菜单权限。
> 目标：从零启动本地环境，完成 UAP 导入、11 个页面主流程联调与验收取证。

---

## 0. 当前已启动环境（2026-11-18）

| 组件 | 地址 | 状态 |
| --- | --- | --- |
| 后端 | `http://127.0.0.1:8082/hs-api` | 已启动，`local-dev`，Liquibase 已执行 |
| 前端 | `http://localhost:9851/#/data-mixing/dataset/index` | 已启动，Vite 代理到 8082 |
| UAP 菜单/资源 | 测试 UAP | 已创建：12 菜单、89 资源，重复执行全部复用 |
| UAP 角色授权 | — | **待执行**：当前会话 `/role/list`、`/auth/selectedTree` 返回 403，无角色管理权限 |

- 后端日志：`C:\Users\Aurora\AppData\Local\Temp\dm_scan\dm_runtime_backend.log`
- 前端日志：`C:\Users\Aurora\AppData\Local\Temp\dm_scan\dm_runtime_frontend.log`
- 本地前端环境文件：`hsmty-web/.env.development.local`（已被 `*.local` 忽略）
- UAP 抓包文件：`hsmty-module-dm-server/uap.curl`（已被 `.gitignore` 忽略）

> 当前 `local-dev` 模式下页面无需 Cookie；UAP 角色授权需在有角色管理权限的会话中执行（见 3.3）。

---

## 1. 前置条件

| 项 | 要求 |
| --- | --- |
| JDK | 21（`mvn -v` 显示 Java 21） |
| Maven | 3.9.x |
| Node / pnpm | Node 20.19.5 推荐；pnpm 10.17.1（`corepack pnpm -v`） |
| 数据库 | `idg_db`：`192.168.1.102:13306`，账号 `ai`（密码走 Jasypt 配置） |
| Redis | `192.168.1.102:26391-26393` Sentinel |
| UAP | 测试环境可登录，拥有菜单/资源维护权限 |
| 算法 | 同事开发中；未接入时 `data-mixing.algorithm.enabled=false`，异步任务会明确失败（预期行为） |

> 本机 Node 24 可运行，但 `vue-tsc` 默认堆内存会 OOM，见第 6 节。

---

## 1. 后端启动

### 1.1 构建

```bash
cd hsmty-module-dm-server

# 首次：把根 POM 安装到本地仓库（子模块 parent 从仓库解析）
mvn -o -N install -DskipTests -s settings.xml \
  -Dmaven.repo.local=C:\Users\Aurora\.m2\repository

# 构建
mvn -o clean package -DskipTests -s settings.xml \
  -Dmaven.repo.local=C:\Users\Aurora\.m2\repository
```

> `settings.xml` 的 `localRepository` 指向本机不存在的 `/ruanjian/maven/repository`，必须用
> `-Dmaven.repo.local` 复用已有依赖；如本机路径不同，按实际替换。

### 1.2 首次启动（执行 Liquibase）

```bash
java -jar hsmty-module-dm-start/target/hsmty-module-dm-start.jar \
  --server.port=8082 \
  --spring.profiles.active=local-dev \
  --spring.liquibase.enabled=true
```

预期：

- 日志出现 `Register API prefix module=data-mixing, prefix=/data-mixing`；
- Liquibase 执行 30+ changeSet，创建 28 张 `hs_data_mixing_*` 表；
- 分类树 v1 初始化 794 节点（content 423 / domain 272 / ability 99），首次约 2 分钟；
- `Started RunApplication`。

首次完成后，日常启动把 `--spring.liquibase.enabled` 改回 `false`（或删除），启动约 12–20 秒。

### 1.3 验证

```bash
curl -s http://127.0.0.1:8082/hs-api/actuator/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/hs-api/v3/api-docs/data-mixing
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8082/hs-api/data-mixing/taxonomy/tree?treeType=content"
```

预期：health `{"status":"UP"}`；OpenAPI 200（当前 101 条路径）；分类树 200。

数据库核对：

```sql
SELECT COUNT(*) FROM information_schema.tables
 WHERE table_schema='idg_db' AND table_name LIKE 'hs_data_mixing_%'; -- 28
SELECT COUNT(*) FROM hs_data_mixing_taxonomy_node;                     -- 794
SELECT COUNT(*) FROM hs_data_mixing_taxonomy_version WHERE status='active'; -- 1
```

> 二次启动应无新 changeSet（`Run: 0`），否则按第 7 节排查。

---

## 2. 前端启动

### 2.1 安装与启动（本地独立壳）

```bash
cd hsmty-web
corepack pnpm install

# 本机已创建 .env.development.local（被 *.local 忽略），内容：
# VITE_PORT=9851
# VITE_API_PROXY_TARGET=http://127.0.0.1:8082
# VITE_OPEN=false
# VITE_LOCAL_MODULES=data-mixing
corepack pnpm dev
```

访问：

```text
http://localhost:9851/#/data-mixing/dataset/index
http://localhost:9851/#/data-mixing/taxonomy/index
...
```

说明：

- 如不使用本地 env 文件，也可用 `VITE_PORT=9851 VITE_API_PROXY_TARGET=http://127.0.0.1:8082 corepack pnpm dev`。
- `VITE_API_PROXY_TARGET` 是 Vite 代理目标；不设置时 `/hs-api` 请求不会转发到本地后端。
- `VITE_LOCAL_MODULES=data-mixing` 只在本机独立壳显示 DM 模块，避免加载其它模块的菜单/接口。
- 后端使用 `local-dev` 时，`/data-mixing/**` 免登录并注入全部 DM 权限；前端在独立壳中 `can()` 默认放行。

### 2.2 主应用（qiankun）联调

- 后端**不要**加 `--spring.profiles.active=local-dev`，使用平台 SSO Cookie。
- UAP 菜单导入并授权后，从主应用进入「数据配比」分组。
- 页面 URL 形如 `/sdom-hsmty/#/data-mixing/ratio-plan/index`。

---

## 3. UAP 菜单与权限导入

> 采用你此前的方式：浏览器手动复制 cURL，脚本模拟请求；Cookie 只保存在本地文件/环境变量，不提交。

### 3.1 抓取 cURL

1. 登录测试环境 UAP。
2. F12 → Network，触发任一 UAP 请求（如 `/uap-manager/auth/allTree`）。
3. 右键 → Copy → Copy as cURL (bash)。
4. 保存为 `hsmty-module-dm-server/uap.curl`（已加入 `.gitignore`）。

要求：cURL 中包含 `Cookie: ...ALLSESSION=...`，URL 包含 `/uap-manager`。

### 3.2 只读预检（dry-run）

```bash
cd hsmty-module-dm-server
python tools/uap/import_dm.py --curl-file uap.curl
```

预期输出：

- `菜单: 12 条；资源: 89 条`（1 个分组 + 11 个页面；89 个权限码）；
- 根菜单 `YD数据平台` 解析成功；
- 逐条打印 `[将创建菜单]` / `[复用菜单]`、`[将创建资源]` / `[复用资源]`；
- 不写任何数据。

### 3.3 执行导入 + 角色授权

```bash
python tools/uap/import_dm.py --curl-file uap.curl --role-name test001 --execute
```

> **本次已执行（2026-11-18）**：12 个菜单、89 个资源已创建，资源 code/value 已校正为权限码；重复执行全部复用。
> **角色授权未执行**：当前会话访问 `/role/list`、`/auth/selectedTree` 返回 403，无角色管理权限。
> 请在 UAP「角色管理 → 分配菜单」给测试角色勾选「数据配比」及 11 个页面；或换有权限的会话执行：
>
> ```bash
> python tools/uap/import_dm.py --curl-file uap.curl --role-name <角色名> --execute
> python tools/uap/import_dm.py --curl-file uap.curl --role-id <角色ID> --execute
> ```

- 角色也可用 `--role-id <uuid>`；不指定角色则只创建菜单/资源，不授权。
- 脚本会先读取 `auth/selectedTree` 的已选菜单并合并，避免覆盖其它模块菜单。
- 默认 `resourceIds` 使用单个逗号分隔字符串；如目标环境只接受重复字段，加 `--repeat-fields`。

### 3.4 后置检查

```bash
python tools/uap/check_permissions.py
```

预期：`结果: PASS`；后端 89 个权限码、清单 89 个、前端 `can()` 58 个、11 个菜单 component 全部一致。

人工检查：

1. 退出并重新登录平台；
2. `permissions/verify` 返回包含 `data-mixing:*`；
3. `auth/selectedTree?roleId=<角色ID>` 勾选「数据配比」及 11 个页面；
4. 侧边菜单可见，逐页打开无白屏。

### 3.5 常见失败

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `flag=false` / HTTP 401 | Cookie 过期 | 重新抓 cURL |
| `saveWithResourceToRole` 必填为空 | 环境只接受重复字段 | 加 `--repeat-fields` 重跑 |
| 菜单不显示 | 角色未做 `role/disAuth` | 用 `--role-name` 重跑，或检查 selectedTree |
| 菜单白屏 | component 与 register key 不一致 | 运行 `check_permissions.py` 核对 |
| 资源 code 是数字 | 保存时未传 code/value | 重跑脚本，按名称复用并修正 |
| 重复资源 | 多次手工创建 | 查 `resource/list`，清理无引用重复项 |

---

## 4. 页面联调顺序与预期

> 算法未接入时，打标/画像/仿真/生产/分析的异步任务会进入 `failed`，`errorCode=ALGORITHM_UNAVAILABLE`，这是**预期行为**，用于验证失败语义与状态机，不是缺陷。

| # | 页面 | 操作 | 预期 |
| --- | --- | --- | --- |
| 1 | 分类体系管理 | 切换内容/领域/能力树；新增根节点/子节点；编辑；启停；删除 | 内容树 30 根、领域 272 根、能力 99 根；路径唯一校验生效；删除有子节点被拒 |
| 2 | 分类体系管理 | 版本管理 → 新建版本快照 → 设为生效 → 版本差异 | 节点数 794；切换后树正常；差异计数正确 |
| 3 | 数据接入与标准化 | 新建数据集 → 上传 `.jsonl/.txt` → 查看文件 → 下载 → 启用 | 文件 SHA-256 去重；重复上传 409；统计文件数/大小正确 |
| 4 | 数据打标 | 选可用数据集 → 新建任务（自动初标）→ 启动 | 任务约 1 秒 `failed`，错误信息可读；不悬挂在 running |
| 5 | 数据打标 | 查看详情/进度/统计/样本 | 统计卡为 0；样本列表为空（算法未接入） |
| 6 | 语料画像分析 | 选数据集 → 查看 7 类画像卡 → 创建并启动 | 文本数据集返回 5 个适用类型；任务明确失败 |
| 7 | 场景管理 | 新建场景 → 勾选标签树（任意层级）→ 启停 → 删除 | 非法标签 400；停用后 options 为空 |
| 8 | 配比方案设计 | 新建方案（2 行 40/60，core≥30）→ 保存 → 详情 → 校验 | 比例合计 100；核心占比、覆盖率校验通过；行库存 0、缺口按目标计算 |
| 9 | 配比方案设计 | 比例 50/30、核心 20%、覆盖 50%、总量超限 | 分别返回 400，消息含具体规则 |
| 10 | 配比方案设计 | 启用 → 复制 → 停用 → 删除 | 启用前强制校验；复制生成“（副本）”草稿 |
| 11 | 配方包管理 | 新建配方包（绑定已启用方案）→ 生成版本 → 发布 → 封存 → 回滚 | 版本快照/差异正确；currentVersion 跟随发布/回滚 |
| 12 | 配方包管理 | 版本行“仿真” → 发起仿真 → 停止/重跑 → 提交判定 | 仿真明确失败；`pass/reject` 在未完成时被拒；`pending` 可记录 |
| 13 | 配比生产任务 | 选配方版本 → 新建并启动 → 详情 Tabs → 重跑 | 执行记录 attempt 1/2；产物/算子/流转为空；任务与执行同为 failed |
| 14 | 配比分析任务 | 新建（绑定数据集）→ 启动 → 详情 | 任务失败；无结果时提示“该任务尚无分析结果”；报告按钮禁用 |
| 15 | 风险预警 | 登记 → 编辑 → 处置（handling/closed/ignored）→ 统计 | KPI 与列表状态同步；详情 JSON 正确 |
| 16 | 工具链与专家校验 | 新建校验任务（需已打标样本）→ 复核 → 完成 | 抽样数量正确；复核一致/改判；完成后 Kappa/Alpha/准确率有值 |
| 17 | 全页面 | 无权限账号 | 菜单不可见；直接调接口 403；按钮不可见 |

### 算法未接入时的成功路径演示（仅测试库）

以下 SQL 用于演示“已完成”状态，**不要在生产执行**。请先通过页面创建对应任务，再把 `<id>` 替换为实际 ID。

**① 仿真完成 + 准入通过**

```sql
UPDATE hs_data_mixing_simulation_task
SET status='completed', progress=100,
    seven_dim_json='{"totalScore":87.5,"dimensions":{"quality":90,"coverage":85,"diversity":80}}',
    finish_time=CURRENT_TIMESTAMP, heartbeat_time=CURRENT_TIMESTAMP
WHERE id=<simulationTaskId>;
```

随后在「配方包管理 → 版本 → 仿真」中提交 `pass` 判定。

**② 分析结果 + 报告**

```sql
INSERT INTO hs_data_mixing_analysis_result
(id, task_id, result_type, total_score, metric_count, result_json, threshold_version, del_flag, create_time, update_time)
VALUES (799100000000000001, <analysisTaskId>, 'nine_dim', 86.5, 4,
        '{"coverage":92.4,"diversity":78.1,"quality":{"completeness":95.2,"gini":0.58},"risks":["长尾稀缺"]}',
        'dm-2026-11-18', 'F', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
```

刷新分析详情后，可生成 HTML/Excel 报告并下载；PDF 会明确返回“暂不支持”。

**③ 专家校验样本**

```sql
-- 1) 先建一个打标任务（或用已有任务）
INSERT INTO hs_data_mixing_labeling_task
(id, task_code, dataset_id, dataset_name, tree_version, labeling_mode, status,
 total_count, labeled_count, unclassified_count, review_pending_count, progress,
 confidence_threshold, operator_id, del_flag, create_time, update_time)
VALUES (799200000000000001, 'TEST-LBL-9001', <datasetId>, <datasetName>, 'taxonomy-1013-pending',
        'auto', 'completed', 10, 10, 0, 10, 100, 0.6, 'dm-multimodal-labeling',
        'F', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

-- 2) 插入 10 条已打标样本（label_path 必须是分类树内真实路径）
INSERT INTO hs_data_mixing_sample_label
(id, task_id, dataset_id, sample_id, record_index, modal, label_path, label_name,
 confidence, label_source, review_status, del_flag, create_time, update_time)
VALUES
(799200000000000101, 799200000000000001, <datasetId>, 'S1', 1, 'text', '新闻与资讯/时政新闻', '时政新闻', 0.9, 'auto', 'pending', 'F', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
(799200000000000102, 799200000000000001, <datasetId>, 'S2', 2, 'text', '新闻与资讯/财经新闻', '财经新闻', 0.9, 'auto', 'pending', 'F', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
-- 其余样本按同结构补齐，至少 5 条便于演示
```

之后在「工具链与专家校验」中按打标任务创建校验任务、复核样本并完成校验。

> SQL 中的中文建议用 UTF-8 文件导入（`mysql --default-character-set=utf8mb4 < seed.sql`），避免命令行编码问题。

---

## 5. 验收取证

| 项 | 证据 |
| --- | --- |
| 后端启动 | 日志含 `Register API prefix module=data-mixing`、`Started RunApplication` |
| 数据库 | 28 张表、794 节点、1 个生效版本、Liquibase 二轮 `Run: 0` |
| OpenAPI | `/hs-api/v3/api-docs/data-mixing` 200，101 条路径 |
| UAP | `import_dm.py` dry-run/execute 输出；`check_permissions.py` PASS；重新登录后菜单与 403 验证 |
| 前端构建 | `NODE_OPTIONS=--max-old-space-size=8192 corepack pnpm type-check`、`corepack pnpm build-only` |
| 页面 | 11 页主流程截图；任务失败信息截图（算法未接入）；报告下载文件 |
| 接口 | 关键请求/响应（浏览器 Network 或 curl），包含 400 规则校验与 409 去重 |

---

## 6. 构建与质量命令

```bash
# 后端
mvn -o clean package -DskipTests -s settings.xml -Dmaven.repo.local=C:\Users\Aurora\.m2\repository

# 前端
cd hsmty-web
corepack pnpm install
NODE_OPTIONS=--max-old-space-size=8192 corepack pnpm type-check
corepack pnpm exec eslint src/modules/data-mixing
NODE_OPTIONS=--max-old-space-size=8192 corepack pnpm build-only

# 权限一致性
cd ../hsmty-module-dm-server
python tools/uap/check_permissions.py
```

> Node 24 下不加 `--max-old-space-size=8192` 时 `vue-tsc` 可能 OOM；npm 引擎警告可忽略。

---

## 7. 常见问题

| 现象 | 排查 |
| --- | --- |
| 页面接口 302/HTML | 后端未使用 `local-dev` 且没有 SSO 会话；本地独立壳请加 `--spring.profiles.active=local-dev` |
| 页面 401/403 | 后端已去掉 local-dev；检查 UAP 资源授权、角色菜单授权、重新登录 |
| 接口 404 `/hs-api/data-mixing/...` | 后端 context-path/前缀不正确；确认 `/hs-api` + `/data-mixing` |
| Liquibase 表不存在 | 首次启动未加 `--spring.liquibase.enabled=true`；或连错库 |
| Liquibase 锁表 | 上次进程中断；确认无运行实例后 `UPDATE databasechangeloglock SET LOCKED=0,...` |
| 上传 413 | `spring.servlet.multipart.max-file-size` 或网关上限；默认 1GB |
| 数据打标/生产一直 running | 不应发生；检查算法网关与残留恢复日志（2 分钟心跳） |
| 页面白屏 | `register.ts` key 与 UAP URL 不一致；运行 `check_permissions.py` |
| 长 ID 精度 | 前端类型统一 string，不要 `Number(id)` |
| `pnpm install` 改写 workspace 配置 | 固定 pnpm 10.17.1，禁止提交 `allowBuilds` 占位符 |

---

## 8. 停止与回滚

```bash
# 停止后端：Ctrl+C 或
# Windows: netstat -ano | findstr :8080  ->  taskkill /PID <pid> /F

# 停止前端：Ctrl+C
```

- UAP 回滚：脚本只增不删；如需撤销，按菜单名称在 UAP 停用/删除 DM 菜单与资源，并重新授权角色。
- 数据库回滚：以发布前备份为准；不要手工删除 `hs_data_mixing_*` 表或修改已执行 changeSet。
- 本地测试数据可用页面逻辑删除；物理清理仅限测试库。

---

## 9. 联调完成标准

1. `check_permissions.py` PASS；UAP 菜单可见、无 403。
2. 11 个页面均可打开，列表/表单/详情/操作无报错。
3. 分类树、数据集、场景、方案、配方包/版本链路完整可操作。
4. 打标/画像/仿真/生产/分析在算法未接入时稳定失败且信息可读；注入演示数据后报告/准入/专家校验可走通。
5. 后端构建、前端 type-check/eslint/build 全绿，OpenAPI 101 条。

> 本地壳左侧菜单：优先读取平行语料菜单表；接口不可用或为空时回退到 `register.ts` 静态分组（与 LTP/ASC 本地壳一致）。设置 `VITE_LOCAL_MODULES` 时会跳过菜单表与行业导航请求，避免无关的“网络错误”提示。
