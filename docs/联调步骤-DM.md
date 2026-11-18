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
| 算法 | `http://127.0.0.1:8092` | 已启动，`op-data-mixing`，21/22 算子 ready（speech 缺 torch） |
| UAP 菜单/资源 | 测试 UAP | 旧结构 12 菜单、89 资源已创建；新结构 3 分组 + 11 页面待重跑导入 |
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
| 算法 | `operator/` 已完成；本地按 2.3 启动 8092，后端用 `DM_ALGORITHM_ENABLED=true` 接入；未部署时保持 false，异步任务会明确失败 |

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
  --spring.liquibase.enabled=true \
  --spring.threads.virtual.enabled=false
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
- UAP 菜单导入并授权后，从主应用进入「数据治理」「配比生产」「质量与合规」分组。
- 页面 URL 形如 `/sdom-hsmty/#/data-mixing/ratio-plan/index`。

### 2.3 算法服务（本地 8092）

算法工程 `operator/` 已完成 22 个算子；本地用独立 venv 启动，端口约定 **8092**（ASC 8090、LTP 8091）。

```bash
cd hsmty-module-dm-server/..
python -m venv .venv-operator
.venv-operator/Scripts/python.exe -m pip install \
  fastapi==0.116.1 uvicorn==0.51.0 python-multipart==0.0.32 \
  jsonschema==4.26.0 numpy==2.2.6 pyarrow==26.0.0 \
  pillow==12.0.0 opencv-python==4.12.0.88 jieba==0.42.1

cd operator
PORT=8092 DEVICE=cpu MODEL_BACKEND=idg MAX_UPLOAD_BYTES=1073741824 \
  ../.venv-operator/Scripts/python.exe inference.py
```

验证：

```bash
curl -s http://127.0.0.1:8092/health
curl -s http://127.0.0.1:8092/dm-ratio-computation/healthz
```

预期：`/health` 返回 200（`status=degraded` 也可接受，表示部分算子缺依赖）；
`dm-ratio-computation`、`dm-multimodal-analysis`、`dm-corpus-normalization`、`dm-corpus-profiling`、
`dm-quality-analysis` 的 `ready=true`。

> 本机未放模型权重时：`dm-multimodal-labeling` 会返回 `DEPENDENCY_UNAVAILABLE`（缺 bge-base-zh-v1.5），
> 打标任务会明确失败；画像 `basic`/`quality` 不依赖权重，可完整跑通。
> 需要打标时，把模型仓放到 `D:\models\shared\`（含 bge-base-zh-v1.5），或设置 `WEIGHTS_DIR`，
> 再执行 `python scripts/stage_weights.py` 暂存并校验。

后端启动时打开算法开关（默认关闭，未部署算子池的环境保持关闭）：

```bash
DM_ALGORITHM_ENABLED=true \
DM_ALGORITHM_BASE_URL=http://127.0.0.1:8092 \
DM_ALGORITHM_MAX_UPLOAD_BYTES=1073741824 \
java -jar hsmty-module-dm-start/target/hsmty-module-dm-start.jar \
  --server.port=8082 --spring.profiles.active=local-dev --spring.liquibase.enabled=false \
  --spring.threads.virtual.enabled=false
```

> 本机实测：JDK 21.0.7 + 虚拟线程在高频查询画像总览时出现过 JVM SIGSEGV（exit 139），
> 本地联调先关闭虚拟线程；已用 70+ 次 `/profile/overview` 压测确认稳定。生产是否开启需另做评估。

接入后的执行链：

| 业务动作 | 算子链 | 结果落库 |
| --- | --- | --- |
| 数据打标 | OP-01 多模态解析 → OP-02 标准化 → OP-05 多模态打标 | `hs_data_mixing_sample_label` |
| 语料画像 basic | OP-01 → OP-02 → OP-08 规模/来源/领域画像 | `hs_data_mixing_profile_result` |
| 语料画像 language | OP-01 → OP-02 → OP-09 语言/地域/时效 | 同上 |
| 语料画像 text | OP-01 → OP-02 → OP-10 文本属性/任务适配 | 同上 |
| 语料画像 knowledge | OP-01 → OP-02 → OP-13 知识/热点/风格 | 同上 |
| 语料画像 quality | OP-01 → OP-02 → OP-14 质量/一致性/难度 | 同上 |
| 语料画像 visual | OP-01 → OP-02 → OP-12 图像/视频属性 | 同上 |
| 语料画像 speech | OP-01 → OP-02 → OP-11 语音质量/声学属性 | 同上（需 torch/funasr） |

数据集文件由后端打包 zip 后上传到算子池 `INPUT_DIR/<datasetId>/`，OP-01/OP-02 的中间产物
通过算子池 `outputDir` 传递给下游；业务库只保存最终结果与任务状态。

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

- `菜单: 14 条；资源: 89 条`（3 个分组 + 11 个页面；89 个权限码）；
- 根菜单 `YD数据平台` 解析成功；
- 逐条打印 `[将创建菜单]` / `[复用菜单]`、`[将创建资源]` / `[复用资源]`；
- 不写任何数据。

### 3.3 执行导入 + 角色授权

```bash
python tools/uap/import_dm.py --curl-file uap.curl --role-name test001 --execute
```

> **本次已执行（2026-11-18）**：旧结构 12 个菜单（1 个「数据配比」分组 + 11 个页面）、89 个资源已创建，资源 code/value 已校正为权限码。
> 新结构改为 3 个分组 + 11 个页面：重跑脚本会创建「数据治理」「配比生产」「质量与合规」三个分组，
> 并在这三个分组下按名称复用/创建页面菜单。旧「数据配比」分组及其 11 个页面菜单不会自动删除，
> 导入后请在 UAP 菜单管理中手工删除旧分组，避免侧边栏出现重复入口。
> **角色授权未执行**：当前会话访问 `/role/list`、`/auth/selectedTree` 返回 403，无角色管理权限。
> 请在 UAP「角色管理 → 分配菜单」给测试角色勾选「数据治理」「配比生产」「质量与合规」及各自页面；或换有权限的会话执行：
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
3. `auth/selectedTree?roleId=<角色ID>` 勾选「数据治理」「配比生产」「质量与合规」及各自页面；
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

> 算法已接入（2.3）：数据打标、语料画像会真实调用算子池。
> 本机未放模型权重时，打标在 OP-05 返回 `DEPENDENCY_UNAVAILABLE`，任务会**明确失败**而不是悬挂；
> 画像 `basic`/`quality` 不依赖权重，可跑通并落库。
> 仿真/生产/分析仍只保留网关抽象（上游算子链未接），任务会明确失败，属当前预期。

| # | 页面 | 操作 | 预期 |
| --- | --- | --- | --- |
| 1 | 分类体系管理 | 切换内容/领域/能力树；新增根节点/子节点；编辑；启停；删除 | 内容树 30 根、领域 272 根、能力 99 根；路径唯一校验生效；删除有子节点被拒 |
| 2 | 分类体系管理 | 版本管理 → 新建版本快照 → 设为生效 → 版本差异 | 节点数 794；切换后树正常；差异计数正确 |
| 3 | 数据接入与标准化 | 新建数据集 → 上传 `.jsonl/.txt` → 查看文件 → 下载 → 启用 | 文件 SHA-256 去重；重复上传 409；统计文件数/大小正确 |
| 4 | 数据打标 | 选可用数据集 → 新建任务（自动初标）→ 启动 | 有 bge 权重时 completed，样本落库；无权重时 `failed` + `DEPENDENCY_UNAVAILABLE`，不悬挂在 running |
| 5 | 数据打标 | 查看详情/进度/统计/样本 | 成功时按置信度统计标签、未归类；失败时统计为 0 |
| 6 | 语料画像分析 | 选数据集 → 画像类型 `basic`/`quality` → 创建并启动 | 任务 completed；结果弹窗显示指标数与 `profile` JSON；画像卡出现摘要 |
| 7 | 语料画像分析 | 查看任务列表 → 结果 → 画像总览 | 列表状态 completed；`metricCount`、`summary` 与算子 metrics 一致 |
| 8 | 场景管理 | 新建场景 → 勾选标签树（任意层级）→ 启停 → 删除 | 非法标签 400；停用后 options 为空 |
| 9 | 配比方案设计 | 新建方案（2 行 40/60，core≥30）→ 保存 → 详情 → 校验 | 比例合计 100；核心占比、覆盖率校验通过；行库存 0、缺口按目标计算 |
| 10 | 配比方案设计 | 比例 50/30、核心 20%、覆盖 50%、总量超限 | 分别返回 400，消息含具体规则 |
| 11 | 配比方案设计 | 启用 → 复制 → 停用 → 删除 | 启用前强制校验；复制生成“（副本）”草稿 |
| 12 | 配方包管理 | 新建配方包（绑定已启用方案）→ 生成版本 → 发布 → 封存 → 回滚 | 版本快照/差异正确；currentVersion 跟随发布/回滚 |
| 13 | 配方包管理 | 版本行“仿真” → 发起仿真 → 停止/重跑 → 提交判定 | 仿真明确失败；`pass/reject` 在未完成时被拒；`pending` 可记录 |
| 14 | 配比生产任务 | 选配方版本 → 新建并启动 → 详情 Tabs → 重跑 | 执行记录 attempt 1/2；产物/算子/流转为空；任务与执行同为 failed |
| 15 | 配比分析任务 | 新建（绑定数据集）→ 启动 → 详情 | 任务失败；无结果时提示“该任务尚无分析结果”；报告按钮禁用 |
| 16 | 风险预警 | 登记 → 编辑 → 处置（handling/closed/ignored）→ 统计 | KPI 与列表状态同步；详情 JSON 正确 |
| 17 | 工具链与专家校验 | 新建校验任务（需已打标样本）→ 复核 → 完成 | 抽样数量正确；复核一致/改判；完成后 Kappa/Alpha/准确率有值 |
| 18 | 全页面 | 无权限账号 | 菜单不可见；直接调接口 403；按钮不可见 |

> 画像页交互：首屏自动选中「最近有画像任务」的数据集，不再空白；任务运行中每 3 秒自动轮询，
> 完成后 KPI 卡与任务列表同步刷新。结果弹窗除指标 JSON 外，按画像类型展示来源占比、模态记录数、
> 难度分布、情感极性、语体分布、文本属性 p50 等图表；领域覆盖等缺失指标会明确标注不可用原因。

### 算法三端联调验收（8092）

1. 新建并启用数据集，上传 `docs/算子开发/samples/text/machine_learning.jsonl`（425 条文本）。
2. 创建画像任务：

```bash
curl -s -X POST http://127.0.0.1:8082/hs-api/data-mixing/profile \
  -H "Content-Type: application/json; charset=UTF-8" \
  -d '{"datasetId":<id>,"profileTypes":["basic","quality"],"startNow":true}'
```

3. 轮询进度：`GET /hs-api/data-mixing/profile/{id}/progress`。
   - 预期 20–60 秒内 `completed`、`progress=100`；
   - 算子日志可见 `POST /dm-multimodal-analysis/predict`、`/dm-corpus-normalization/predict`、`/dm-corpus-profiling/predict`、`/dm-quality-analysis/predict`。
4. 查看结果：`GET /hs-api/data-mixing/profile/{id}/result`。
   - `basic`：`scale.recordCount=425`、`sourceDistribution`、`domainCoverage`；
   - `quality`：`completeness`、`gini`、`difficulty`、`polarity` 等 16 项指标。
5. 打标任务：`POST /hs-api/data-mixing/labeling`，`startNow=true`。
   - 有权重：`completed`，`GET /labeling/{id}/samples` 返回样本；
   - 无权重：`failed`，`errorMessage` 包含 `DEPENDENCY_UNAVAILABLE` 与缺失模型路径。

> 本机已实测：画像 `basic` 10 项指标、`quality` 16 项指标，任务 completed 并落库；
> 打标在无 bge 权重时按预期失败。

### 其它未接算子链的演示（仅测试库）

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
| 画像/打标失败 `TRANSPORT_ERROR` | 算子池未启动或端口不符；`curl http://127.0.0.1:8092/health`，核对 `DM_ALGORITHM_BASE_URL` |
| 打标失败 `DEPENDENCY_UNAVAILABLE` | 缺 bge-base-zh-v1.5 / torch 等依赖；按 2.3 放权重或改用画像流程 |
| 上传失败 `UPLOAD_TOO_LARGE` | 后端 `DM_ALGORITHM_MAX_UPLOAD_BYTES` 与算子池 `MAX_UPLOAD_BYTES` 要同时调大 |
| 画像 completed 但无结果 | 查 `hs_data_mixing_profile_result.task_id`；解析失败会转 task failed，不会 completed |
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
