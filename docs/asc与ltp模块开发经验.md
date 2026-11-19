# 数据配比（DM）模块开发规范（完整版）

| 文档信息 | 内容 |
| --- | --- |
| 文档名称 | 数据配比（DM）模块开发规范 |
| 版本 / 日期 | V1.0 / 2026-11-16 |
| 适用范围 | `hsmty-module-dm-server`（后端）、`hsmty-web/src/modules/dm`（前端）、DM 算法对接、UAP 菜单权限、测试与部署 |
| 依据 | 平台《前后端规范 CLAUDE.md》、《平台 UI 样式设计规范 V4-1025》、《平台相关 ID 生成规范 1026》、LTP 需求/技术设计/契约、ASC 契约与上线检查单 |
| 状态 | 规范正文可直接执行；第 13 章 DM 领域蓝图待需求评审确认后冻结 |

---

## 0. 阅读指南

### 0.1 一句话

DM 按目标比例，从多个数据池中抽取、去重、质量过滤并混合，产出**可追溯、可复现、可版本化**的数据集；工程上完全复用 hsmty 模块模板、平台 UI、UAP 权限、SSO Cookie 与算法服务对接模式。

### 0.2 强制等级

| 标记 | 含义 |
| --- | --- |
| 【强制】 | 违反即打回；代码评审、提测、上线均按此检查 |
| 【推荐】 | 默认这样做；不这样做需要在 PR/ADR 中说明原因 |
| 【可选】 | 按业务需要选择 |

### 0.3 文档结构

| 章节 | 内容 | 读者 |
| --- | --- | --- |
| 1 | 总则、边界、角色、交付物 | 全员 |
| 2 | 模块接入与命名 | 后端 / 前端 / 平台对接人 |
| 3 | 后端开发规范 | 后端 |
| 4 | 数据库与 Liquibase | 后端 |
| 5 | 接口契约 | 后端 / 前端 |
| 6 | 异步任务与状态机 | 后端 / 前端 |
| 7 | 算法服务集成 | 后端 / 算法 |
| 8 | 前端开发规范 | 前端 |
| 9 | 权限、菜单与 UAP | 后端 / 平台管理员 |
| 10 | 测试与验收 | 后端 / 前端 / 测试 |
| 11 | 部署与上线 | 后端 / 运维 |
| 12 | 文档与协作 | 全员 |
| 13 | DM 领域蓝图 | 产品 / 后端 / 前端 |
| 14 | 检查清单 | 全员 |
| 15 | 经验与反模式 | 全员 |

### 0.4 与需求文档的关系

- 本规范回答“**怎么做才符合平台和团队标准**”，不替代需求说明书。
- 第 13 章的领域模型、表、接口、页面是**建议基线**；需求评审后如与本规范冲突，先改需求/契约，再改代码。
- 契约以 `contract/api-contract.md` 为唯一事实源；本文与契约不一致时，以契约 + 父会话裁决为准。

---

## 1. 总则

### 1.1 模块定位

数据配比模块属于「高质量数据供给和管理平台」的业务子系统，建议菜单名「数据配比」。核心能力：

1. **数据池**：把可参与配比的数据集/素材组织成可管理、可统计、可版本化的集合。
2. **配比方案**：定义“从哪些池、按什么比例、经过什么质量/去重规则、产出多少条”的可复用方案。
3. **配比任务**：按方案快照异步执行抽样与混合，过程可观测、可停止、可重跑。
4. **配比结果**：产出数据集文件/清单，记录目标比例、实际比例、偏差、质量报告与哈希。
5. **数据集版本**：把结果发布为不可变版本，供训练/评测/供给使用。

### 1.2 与其他模块的边界

| 关注点 | DM 负责 | 不负责 |
| --- | --- | --- |
| 登录 / 用户 / 角色 | 使用平台 SSO 与 UAP 权限 | 不自建登录、用户表、角色表 |
| 数据生产 | 消费已有数据池/数据集 | 不生产原始攻击样本（ASC）、不做数据价值评测（LTP） |
| 数据评测 | 可调用质量/统计能力 | 不替代 LTP 的 5 维 10 指标评测 |
| 算法计算 | 提交任务、轮询、落库、展示 | 不在业务库复制算法产物；不把大文件写进数据库 |
| 文件存储 | 通过存储抽象保存文件/引用 | 不把 OSS 密钥、共享目录路径暴露给前端 |
| 其他模块数据 | 通过 Feign client 或公开 API 读取 | 不直连其他模块数据库、不 join 其他模块表 |

### 1.3 五条铁律

1. **契约先行**：接口、枚举、字段、状态先写进 `contract/`，前后端按契约开发，不臆造字段。
2. **状态机先行**：所有异步任务必须有明确状态、合法迁移、终态、恢复策略；禁止“只有 running 和完成”。
3. **算法是计算事实源**：业务库只存 `jobId`、摘要、版本、产物 URI；评分/抽样结果以算法返回为准。
4. **可追溯**：方案快照、输入池快照、随机种子、算法版本、输出哈希、操作人缺一不可。
5. **三处一致**：权限码在 `@PreAuthorize`、UAP 菜单 `permissions`、前端 `can()` 三处完全一致；菜单 `component` 与 `register.ts` key 完全一致。

### 1.4 角色与协作

| 角色 | 职责 |
| --- | --- |
| 父会话 / 架构 | 维护契约、ADR、跨模块裁决、版本与上线节奏 |
| 后端 | 领域模型、接口、数据库、异步任务、算法对接、权限点 |
| 前端 | 模块注册、页面、ProTable、弹窗/抽屉、权限与轮询 |
| 算法 | 提供带版本的 HTTP 契约、任务状态、产物、错误码、健康检查 |
| 平台/UAP | 菜单、权限资源、角色授权、字典号段、菜单号段 |
| 运维 | 测试/生产环境、数据库、Redis、Jenkins、Ingress、存储 |

### 1.5 交付物清单

| 交付物 | 位置 | 完成标准 |
| --- | --- | --- |
| 需求说明书 | `docs/design/01-需求说明书-DM.md` | 范围、角色、流程、状态、边界明确 |
| 技术设计 | `docs/design/02-技术设计-DM.md` | 表、接口、任务、算法、异常、部署 |
| 功能追溯矩阵 | `docs/design/03-功能追溯矩阵-DM.md` | 每条需求有实现、验证、状态 |
| 接口契约 | `contract/api-contract.md`、`enums.md`、`auth.md`、`algorithm-integration.md` | 前后端评审通过 |
| OpenAPI | `contract/openapi.json` | 后端导出，不手改 |
| 权限清单 | `docs/UAP权限注册清单-DM.md` | 与 `@PreAuthorize` 逐条一致 |
| 部署清单 | `contract/deployment-checklist.md` | 环境变量、Liquibase、冒烟、回滚 |
| 验收脚本 | `tools/local-smoke/*.py` | 可重复执行、自动清理 |
| 构建记录 | `docs/BUILD-INFO.md` | 版本、产物、哈希、测试结果 |

---

## 2. 模块接入与命名

### 2.1 先申请，再开发

平台命名规范要求每个业务独占表前缀、接口地址、包名、服务名、菜单号段、字典号段。DM 开工前必须完成下表确认；**未确认前可以用 `dm` 占位做技术验证，但不要建正式菜单、不要对外发布**。

| 项 | 建议值 | 确认方 | 说明 |
| --- | --- | --- | --- |
| 产品/研发模块名 | 数据配比 | 产品 | 菜单与文档统一名称 |
| 模块短名 / domain | `dm` | 平台命名维护方 | 小写单段；与仓库名一致 |
| 根 artifactId | `hsmty-module-dm-server` | 平台 | 已有仓库名 |
| 子模块 | `hsmty-module-dm-client/core/start` | 后端 | 模板改名 |
| Java 包 | `com.hsmty.dm` | 平台 | 与模板 `com.hsmty.xxx` 对应 |
| API 前缀 | `/hs-api/dm` | 平台 | 其他模块用连字符，如 `/hs-api/value-lab` |
| 表前缀（二级） | `dm_` | 平台 | 完整表名 `hs_dm_*` |
| 权限码前缀 | `dm:` | 平台 | 如 `dm:plan:create` |
| 字典类型前缀 | `dm_` | 平台 | 如 `dm_task_status` |
| 服务名 | `hsmty-dm-server` | 平台 | Feign `name` |
| 菜单号段 | 待申请 | 平台 | 18 位独立号段 |
| 字典来源/类型号段 | 待申请 | 平台 | 不复用 LTP/ASC |
| 业务编号前缀 | `POOL` / `PLAN` / `MTK` / `MIX` / `MDS` | 平台 | 2–4 位大写，登记后使用 |
| 数据库 | 待确认 | 运维 | 模板默认 `sd_data_engineering`；LTP/ASC 使用 `idg_db`，以测试环境为准 |

> 【强制】命名确认结果写入 `contract/naming-alignment.md` 或 ADR；未确认的命名不得扩散到菜单、表、接口。

### 2.2 工程改名清单（`xxx` → `dm`）

| 位置 | 模板值 | 改为 |
| --- | --- | --- |
| 根 POM `artifactId` | `hsmty-module-xxx-server` | `hsmty-module-dm-server` |
| 子模块 artifactId | `hsmty-module-xxx-client/core/start` | `hsmty-module-dm-*` |
| Java 包 | `com.hsmty.xxx` | `com.hsmty.dm` |
| 启动类 | `com.hsmty.RunApplication` | 保持 `com.hsmty` 根包，扫描 `com.hsmty.dm` |
| API 前缀配置 | `XxxApiPrefixConfiguration` | `DmApiPrefixConfiguration`，`module=dm`、`prefix=/dm`、`basePackages=com.hsmty.dm` |
| MapperScan | `XxxMapperScanConfiguration` | `DmMapperScanConfiguration`，只扫 `com.hsmty.dm.mapper` |
| springdoc group | `xxx` | `dm`，`packages-to-scan: com.hsmty.dm` |
| 配置前缀 | `hsmty.api-prefix.modules.xxx` | `hsmty.api-prefix.modules.dm` |
| Feign 地址 | `xxx.service.url` | `dm.service.url` |
| Liquibase 目录 | `db/changelog/xxx/` | `db/changelog/dm/` |
| 模块 changelog | `module-xxx-changelog.xml` | `module-dm-changelog.xml` |
| 表名 | `xxx_table` | `hs_dm_*` |
| 权限码 | `xxx:*` | `dm:*` |
| 前端模块 | `src/modules/xxx` | `src/modules/dm` |

【强制】改名后全局搜索 `xxx`、`Xxx`、`charging`、`充电站`，不得残留模板文案。

### 2.3 后端目录结构

```text
hsmty-module-dm-server/
├── hsmty-module-dm-client/
│   └── com.hsmty.dm
│       ├── feign/                       # 供其他服务调用 DM
│       └── pojo/dto、pojo/vo            # 跨服务契约
├── hsmty-module-dm-core/
│   └── com.hsmty.dm
│       ├── config/                      # ApiPrefix、MapperScan、业务配置
│       ├── controller/                  # REST 入口
│       ├── service/、service/impl/      # 业务逻辑
│       ├── mapper/                      # MyBatis-Flex
│       ├── pojo/po、dto、vo、excel/     # 持久化与接口模型
│       ├── task/                        # 异步执行器、任务恢复
│       ├── mixing/                      # 配比算法/编排（领域服务）
│       ├── algorithm/                   # 算法 HTTP 客户端、请求/响应模型
│       ├── storage/                     # 文件存储抽象
│       └── support/                     # 编号、校验、常量、工具
└── hsmty-module-dm-start/
    ├── com.hsmty.RunApplication
    ├── com.hsmty.configuration/         # 全局配置
    └── resources/
        ├── application.yml
        └── db/changelog/changelog-master.xml
```

### 2.4 `application.yml` 最小增量

```yaml
springdoc:
  group-configs:
    - group: 'dm'
      paths-to-match: '/**'
      packages-to-scan: com.hsmty.dm

hsmty:
  api-prefix:
    modules:
      dm:
        enabled: true
        prefix: /dm

dm:
  service:
    url: '${DM_SERVICE_URL:http://127.0.0.1:8080/hs-api}'
  pool:
    allowed-formats: json,jsonl
    max-file-size: 1GB
    max-item-count: 50000
  mixing:
    max-component: 10
    max-target-total: 10000000
    default-seed-length: 8
    ratio-tolerance: 0.01
  task:
    max-concurrent: 4
    heartbeat-seconds: 30
    stale-minutes: 2
    recover-interval-ms: 300000
  algorithm:
    enabled: ${DM_ALGORITHM_ENABLED:true}
    # 示例地址，实际端口/路径由算法侧提供；非密钥配置可直接写明，便于甲方阅读
    base-url: "${DM_ALGORITHM_BASE_URL:http://192.168.1.105:17029/algorithm/v1}"
    internal-token: ${DM_ALGORITHM_INTERNAL_TOKEN:}
    connect-timeout: 3s
    read-timeout: 10s
    upload-timeout: 10m
    poll-interval: 2s
    poll-timeout: 30m
    storage-mode: ${DM_ALGORITHM_STORAGE_MODE:file}
  storage:
    type: local
    local:
      root: ${DM_STORAGE_ROOT:./data/dm}
```

> 【强制】非密钥的算法地址、超时、开关按甲方要求可直接写明，便于甲方工程师阅读；令牌、数据库密码、Redis 密码、OSS 密钥只允许环境变量或 Jasypt。
>
> 【强制】模板中的 `operations-sorter: alpha·` 多余字符必须修正为 `alpha`；`xxx.service.url` 的 `/api` 必须改为 `/hs-api`。

### 2.5 启动验证

```bash
mvn -s settings.xml -pl hsmty-module-dm-core,hsmty-module-dm-start -am clean package -DskipTests
java -jar hsmty-module-dm-start/target/hsmty-module-dm-start.jar \
  --spring.profiles.active=local-dev \
  --spring.liquibase.enabled=true
```

检查：

1. 启动日志出现 `Register API prefix module=dm, prefix=/dm`。
2. `http://localhost:8080/hs-api/v3/api-docs/dm` 可访问，分组为 `dm`。
3. 未登录访问 `/hs-api/dm/pool` 返回 302（本地 `local-dev` 除外）。
4. Liquibase 重复启动幂等。
5. 数据库出现 `hs_dm_*` 表。

---

## 3. 后端开发规范

### 3.1 分层与依赖

```text
start → core → client
```

【强制】

1. `client` 只放 Feign 契约、DTO、VO、降级实现，不放 Controller/Service/Mapper/Entity/配置。
2. `core` 不依赖 `start`，不写 `main`，不引 `spring-boot-maven-plugin`。
3. `core` 中 Web 依赖必须 `provided` + `optional`。
4. 跨服务只能通过对方 `client` 的 Feign 接口；禁止在 `core` 自写 HTTP 客户端调用其他业务服务（算法服务除外，统一走 `algorithm/` 包）。
5. 其他模块不得依赖 DM 的 `core`；只能依赖 `hsmty-module-dm-client`。

### 3.2 Controller

```java
@Tag(name = "配比方案")
@RestController
@RequestMapping("plan")
@RequiredArgsConstructor
@Validated
public class MixingPlanController {

    private final MixingPlanService mixingPlanService;

    @Operation(summary = "分页查询配比方案")
    @PreAuthorize("hasAnyAuthority('dm:plan:page')")
    @GetMapping
    public ApiResult<PageResult<MixingPlanVO>> page(MixingPlanListDTO dto) {
        return ApiPageResult.success(mixingPlanService.page(dto));
    }

    @Operation(summary = "新增配比方案")
    @PreAuthorize("hasAnyAuthority('dm:plan:create')")
    @PostMapping
    public ApiResult<Void> create(@Valid @RequestBody MixingPlanCreateDTO dto) {
        mixingPlanService.create(dto);
        return ApiResult.success();
    }
}
```

【强制】

1. 类上必须有 `@Tag`、`@RestController`、`@RequestMapping`、`@RequiredArgsConstructor`、`@Validated`。
2. 每个方法必须有 `@Operation(summary=...)` 与 `@PreAuthorize`。
3. 返回值统一 `ApiResult` / `ApiPageResult`；分页固定 `ApiResult<PageResult<XxxVO>>`。
4. Controller 只做“接收 → 调 Service → 包装”，禁止业务判断、禁止访问 Mapper、禁止 `try/catch` 拼响应。
5. HTTP 语义：新增 `POST`、修改 `PUT`、删除 `DELETE`、分页/列表 `GET`、详情 `GET /{id}`、业务动作 `POST /{id}/start`。
6. 批量删除 body 用 `SelectIdsDTO { ids: [] }`。
7. 路径变量前不要重复写 `/hs-api` 或 `/dm`；前缀由 `DmApiPrefixConfiguration` 统一加。

### 3.3 Service / ServiceImpl

```java
public interface MixingPlanService extends IService<MixingPlanEntity> {
    void create(MixingPlanCreateDTO dto);
    void update(MixingPlanUpdateDTO dto);
    void remove(SelectIdsDTO dto);
    PageResult<MixingPlanVO> page(MixingPlanListDTO dto);
    MixingPlanVO detail(Long id);
    void publish(Long id);
}
```

```java
@Service
@RequiredArgsConstructor
public class MixingPlanServiceImpl extends ServiceImpl<MixingPlanMapper, MixingPlanEntity>
        implements MixingPlanService {

    private final MixingPlanComponentMapper componentMapper;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void create(MixingPlanCreateDTO dto) {
        validateRatio(dto.getComponents());
        MixingPlanEntity entity = BeanCopyUtils.copy(dto, MixingPlanEntity.class);
        entity.setPlanCode(bizCodeGenerator.nextPlanCode());
        entity.setStatus(PlanStatus.DRAFT.name());
        save(entity);
        saveComponents(entity.getId(), dto.getComponents());
    }
}
```

【强制】

1. Service 接口继承 `IService<Entity>`，实现继承 `ServiceImpl<Mapper, Entity>`。
2. 方法命名固定 `create / update / remove / page / list / detail`；业务动作按动词命名（`publish`、`start`、`stop`、`retry`）。
3. 断言统一 `CommonResponseEnum.XXX.assertTrue(...)` / `assertNull(...)`；错误消息必须可读、可定位。
4. DTO ↔ PO / PO ↔ VO 用 `BeanCopyUtils.copy`；禁止大段手写 `setXxx`。
5. 分页用 `PageUtils.getPage(dto)` / `PageUtils.getPageResult(page)`；查询用 `pageAs`、列表用 `listAs`。
6. 查询条件集中写在 `buildQueryWrapper(XxxListDTO dto)`；非空用 `Utils.isNotNull`，空集合用 `ObjectUtil.isEmpty`。
7. 构造器注入：`@RequiredArgsConstructor` + `private final`；禁止 `@Autowired` 字段注入。
8. 多表/多步写操作加 `@Transactional(rollbackFor = Exception.class)`。
9. 事务方法内禁止调用远程服务、上传大文件、执行长耗时算法；这些操作放到事务提交后或异步任务。
10. 不在 Service 直接操作 `RedisTemplate`，统一 `RedisCache`。

### 3.4 Mapper / PO

```java
@Data
@Table(value = "hs_dm_mixing_plan",
       onInsert = EntityChangeListener.class,
       onUpdate = EntityChangeListener.class)
@Schema(description = "配比方案")
public class MixingPlanEntity extends BaseEntity {

    @Schema(description = "方案业务编号")
    private String planCode;

    @Schema(description = "方案名称")
    private String name;

    @Schema(description = "状态：draft/enabled/disabled")
    private String status;
}
```

【强制】

1. 所有业务表 PO 继承 `BaseEntity`（`id/createId/createTime/updateId/updateTime/delFlag`）。
2. 主键 `Long` + `@Id(keyType = KeyType.Generator, value = SzIdGenerator.NAME)`，禁止自增/手动赋值。
3. `@Table` 必须挂 `EntityChangeListener`，审计字段由框架填充，业务代码不手写。
4. 禁止物理删除；`delFlag` 标 `@Column(isLogicDelete = true)`，正常 `F`、删除 `T`。
5. 每个字段带 `@Schema(description=...)`；状态字段用 `String` 存字典 alias，禁止魔法数字。
6. 表名、字段名与 Liquibase、Mapper XML 三处一致；`auto-mapping-unknown-column-behavior: none` 下多一列会报错。
7. Mapper 继承 `BaseMapper<Entity>`，不加 `@Mapper`；简单查询 `QueryWrapper`，复杂 SQL 才写 XML。
8. XML 必须提供 `BaseResultMap` 与 `Base_Column_List`，新增字段同步两处。

### 3.5 DTO / VO / Excel

| 类型 | 用途 | 规则 |
| --- | --- | --- |
| `XxxCreateDTO` | 新增入参 | 只放入口字段；必填 `@NotNull/@NotBlank`；不暴露审计字段 |
| `XxxUpdateDTO` | 修改入参 | 必须含 `id`；其余同新增 |
| `XxxListDTO` | 查询入参 | `extends PageQuery`；字段可空 |
| `XxxVO` | 出参 | 可含展示冗余字段；不得直接返回 PO |
| `XxxExcel` | 导入导出 | `@ExcelProperty` / `@ExcelIgnore` / `@DictFormat`；与 VO 分离 |

【强制】

1. 所有字段带 `@Schema`；时间字段按需 `@DateTimeFormat(pattern="yyyy-MM-dd HH:mm:ss")`。
2. 查询 DTO 继承 `PageQuery`，分页参数 `page/limit`。
3. 新增/修改 DTO 不暴露 `createId/createTime/updateId/updateTime/delFlag`。
4. 校验用 `jakarta.validation`；复杂规则（比例和、组分唯一、数量范围）写自定义校验器或在 Service 首行显式校验。
5. VO 的 `Long` 主键按 string 返回：`@Schema(type="string")`，并确认平台 Jackson 配置生效。

### 3.6 校验、异常与返回

```java
CommonResponseEnum.INVALID.message("配比方案至少需要 2 个组分")
        .assertTrue(components == null || components.size() < 2);
CommonResponseEnum.INVALID.message("组分比例合计必须为 100")
        .assertTrue(abs(sum - 100) > 0.01);
CommonResponseEnum.NOT_EXISTS.message("配比方案不存在").assertNull(entity);
```

【强制】

1. 业务异常统一抛 `CommonResponseEnum` 或模块异常枚举；由全局异常处理器转 `ApiResult`。
2. Controller 禁止 `try/catch` 后自行拼 JSON；Service 捕获异常必须记录日志或转业务异常，禁止吞异常。
3. 错误消息面向用户，包含“哪个字段/哪个对象/什么规则”，不要只写“参数错误”。
4. 系统异常日志必须带异常对象：`log.error(e.getMessage(), e)`。
5. 不得把算法原始错误栈、SQL、文件路径直接返回前端。

### 3.7 事务

【强制】

1. 只把数据库写操作放进事务；远程调用、文件上传、算法轮询放事务外。
2. 需要“提交后再投递任务”时使用 `TransactionSynchronizationManager.registerSynchronization(afterCommit)` 或 Spring 事件 `@TransactionalEventListener(AFTER_COMMIT)`。
3. 同一事务内不要读写不同数据源；不要跨模块事务。
4. 批量插入使用 `saveBatch` 或分批（每批 500–1000），避免长事务。
5. 事务方法不要 `private` 自调用（AOP 失效）。

### 3.8 并发与幂等

【强制】

1. 任务启动/停止使用 `UPDATE ... WHERE id=? AND status=?` 的 CAS 更新，检查影响行数；不要“先查后改”裸奔。
2. 同一业务对象的关键操作加锁：单机用按 ID 分桶的 `Object[] locks`，多副本用 Redis 分布式锁；锁内重新读取状态再判断。
3. 异步任务提交必须幂等：同一实验/任务重复点击“启动”返回同一任务或明确提示“已在运行”。
4. 异步创建接口支持 `Idempotency-Key` 请求头，值用业务任务号；服务端记录 key，重复请求返回首次结果。
5. 状态落库前再次校验当前状态，防止“停止后被完成覆盖”的竞态（LTP 真实事故）。
6. 多副本部署时雪花 `worker-id` 每实例不同，否则主键冲突。

### 3.9 逻辑删除与审计

【强制】

1. 所有业务表逻辑删除；不使用 `DELETE FROM`。
2. `del_flag` 默认 `F`，删除置 `T`；查询默认带 `del_flag='F'`（MyBatis-Flex 逻辑删除自动处理）。
3. 审计字段由 `EntityChangeListener` 填充；业务代码不手写 `createTime/updateTime`。
4. 唯一索引与逻辑删除冲突：如果业务编号需要“删除后可重建”，不要建“唯一索引 + 逻辑删除”；改用普通索引 + 应用层校验，或增加 `active_flag` 参与唯一索引。
5. 关联表、结果表使用普通索引，重跑时先逻辑删除旧结果再插入，避免唯一索引阻挡。

### 3.10 查询、分页与性能

【强制】

1. 列表默认分页，禁止无上限 `list()` 全表返回；下拉选项最多 50–200 条并支持 keyword。
2. 查询条件集中构建，避免 Controller/Service 到处拼 `QueryWrapper`。
3. 避免 N+1：批量查询用 `in`，或一次聚合；关联名称通过批量查询回填。
4. 大文件统计/预览流式读取，禁止 `readAllBytes()`；分页预览只读前 N 行。
5. 导出/下载走流式响应，设置 `Content-Disposition`，不要先全量加载内存。
6. 慢查询看执行计划；状态、业务编号、外键、时间范围字段建索引。
7. 统计类接口可缓存 30–60 秒；任务进度不要缓存。

### 3.11 缓存

【推荐】

1. 统一 `RedisCache`，key 规范 `dm:{resource}:{id}:{version}`，例如 `dm:plan:1001:v3`。
2. 只缓存读多写少、可容忍短暂不一致的数据（字典、选项、统计）；权限、任务状态不缓存。
3. 更新/删除时主动失效；设置 TTL（5–30 分钟），不要永久 key。
4. 缓存空值防穿透，TTL 短（1–5 分钟）。
5. 缓存值变化必须升版本或改 key，避免旧结构反序列化失败。

### 3.12 日志与可观测

【强制】

1. 使用 `@Slf4j`，禁止 `System.out.println`（启动 Banner 例外）。
2. 关键链路日志字段：`traceId`、`taskCode`、`planCode`、`poolCode`、`jobId`、`stage`、`costMs`、`result`。
3. 禁止记录：Cookie、Token、密码、完整请求体、完整数据记录、算法密钥、文件内容。
4. 算法调用只记录 `jobId`、阶段、耗时、错误码；错误响应截断到 500 字以内。
5. 暴露 `/hs-api/actuator/health`，只开 health，不暴露 env/beans；算法/存储健康作为自定义 indicator。
6. 任务表本身就是可观测数据源：进度、当前步骤、心跳、错误消息必须及时更新。

### 3.13 安全

【强制】

1. 文件上传校验扩展名、MIME、大小、空文件、UTF-8；文件名清洗，禁止路径穿越（`../`、绝对路径）。
2. 文件存储 key 由后端生成，不使用用户文件名作为物理路径。
3. 下载必须校验权限与对象归属；不允许通过猜 ID 下载他人数据。
4. 前端不直连算法服务；算法地址、令牌只在后端。
5. SQL 用 MyBatis-Flex 参数绑定，禁止字符串拼接。
6. 生产关闭 Swagger；`springdoc.swagger-ui.enabled=false`、`springdoc.api-docs.enabled=false`。
7. 生产必须注入 `JASYPT_ENCRYPTOR_PASSWORD`，不得使用默认 `datasource`。
8. 日志脱敏；导出文件不包含敏感字段。

### 3.14 代码风格

【强制】

1. UTF-8、LF、Java 4 空格、YAML/前端 2 空格。
2. 包名小写；类名大驼峰；方法/变量小驼峰；常量全大写下划线。
3. Lombok：`@Data`、`@Slf4j`、`@RequiredArgsConstructor`；不手写 getter/setter。
4. 类、接口、public 方法写 Javadoc（`<p>`、`@author`、`@since`）。
5. 空值判断 `Utils.isNotNull` / `ObjectUtil.isEmpty`。
6. 超过 3 层 `if` 提前 return 或抽方法；集合处理优先 Stream，但不牺牲可读性。
7. 避免魔法值：状态、权限码、路径、阈值提取常量/枚举/配置。
8. Java 21 可用 record、文本块、模式匹配、虚拟线程，但以可读性优先。
9. 注释与 `@Schema` 必须与业务一致，禁止保留模板“充电/charging”。

### 3.15 后端测试

【强制】

1. 业务逻辑测试放 `core`；装配/集成测试放 `start`；`client` 不写测试。
2. JUnit 5 + AssertJ + `spring-boot-starter-test`。
3. 默认 `skipTests=true`，回归必须显式 `-DskipTests=false`，并确认用例真的执行。
4. 集成测试用 `@SpringBootTest(webEnvironment=NONE, properties={...})` 注入最小配置，不依赖本地 `application.yml`。
5. 至少覆盖：正常流程、参数校验失败、状态非法迁移、逻辑删除隔离、幂等、并发启动、任务恢复。

---

## 4. 数据与数据库规范

### 4.1 表设计模板

```sql
CREATE TABLE hs_dm_mixing_plan (
  id            BIGINT       NOT NULL COMMENT '主键ID',
  plan_code     VARCHAR(16)  NOT NULL COMMENT '方案业务编号',
  name          VARCHAR(100) NOT NULL COMMENT '方案名称',
  scene_code    VARCHAR(50)  NULL COMMENT '目标场景编码',
  status        VARCHAR(20)  NOT NULL DEFAULT 'draft' COMMENT '状态：draft/enabled/disabled',
  version_no    INT          NOT NULL DEFAULT 1 COMMENT '方案版本号',
  config_json   LONGTEXT     NULL COMMENT '方案配置快照JSON',
  description   VARCHAR(1000) NULL COMMENT '方案说明',
  create_id     BIGINT       NULL COMMENT '创建人ID',
  create_time   DATETIME     NULL COMMENT '创建时间',
  update_id     BIGINT       NULL COMMENT '更新人ID',
  update_time   DATETIME     NULL COMMENT '更新时间',
  del_flag      CHAR(1)      NOT NULL DEFAULT 'F' COMMENT '删除标记：F正常 T已删除',
  PRIMARY KEY (id),
  KEY idx_dm_plan_code (plan_code),
  KEY idx_dm_plan_status (status),
  KEY idx_dm_plan_scene (scene_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='配比方案';
```

### 4.2 命名与字段规则

| 对象 | 规则 | 示例 |
| --- | --- | --- |
| 表 | `hs_{业务前缀}_{对象}`，snake_case | `hs_dm_mixing_task` |
| 列 | snake_case，Java 驼峰 | `target_total` → `targetTotal` |
| 主键 | `id BIGINT`，雪花 | — |
| 业务编号 | `{对象}_code VARCHAR(16)` | `plan_code` |
| 状态 | `status VARCHAR(20)`，存字典 alias | `running` |
| 金额/比例 | `DECIMAL(18,6)` / `DECIMAL(6,3)` | `ratio DECIMAL(6,3)` |
| 布尔 | `CHAR(1)` `T/F`（DB），API boolean | `applicable` |
| 时间 | `DATETIME`，API `yyyy-MM-dd HH:mm:ss` | — |
| JSON | `LONGTEXT` + 应用层序列化 | `plan_snapshot` |
| 文件 | 存 `file_key`/URI + 大小 + 哈希，不存字节 | `manifest_uri` |

【强制】

1. 所有业务表带公司前缀 `hs_` 与业务前缀 `dm_`；禁止 `user`、`order`、`config` 等无前缀表。
2. 表、列必须有 `COMMENT`；主键、非空、默认值显式声明。
3. 外键不建数据库 FK（平台惯例），由应用层保证；但必须建索引。
4. 不用数据库保留字；不用复数表名；不用拼音缩写（除已登记前缀）。
5. 状态字段不用数字；API 与 DB 都用小写英文 alias。

### 4.3 索引规则

| 场景 | 索引 |
| --- | --- |
| 业务编号查询 | `UNIQUE` 或普通索引（视逻辑删除策略） |
| 外键/关联查询 | 普通索引，如 `pool_id`、`plan_id`、`task_id` |
| 列表筛选 | `(status, create_time)` 组合索引 |
| 时间范围 | `create_time` / `finish_time` |
| 哈希去重 | `content_hash` 普通索引 |
| 任务恢复 | `(status, heartbeat_time)` |

【强制】上线前用 `EXPLAIN` 检查核心列表 SQL；避免 `%keyword%` 前置模糊导致全表扫描（数据量大时改全文/搜索引擎）。

### 4.4 Liquibase

文件位置：

```text
hsmty-module-dm-core/src/main/resources/db/changelog/dm/
├── 001_dm_init.xml
├── 002_dm_dict_init.xml
├── 003_dm_menu_init.xml
├── 004_dm_add_xxx.xml
└── ...
hsmty-module-dm-core/src/main/resources/db/changelog/module-dm-changelog.xml
hsmty-module-dm-start/src/main/resources/db/changelog/changelog-master.xml
```

模板：

```xml
<changeSet id="dm-create-plan-20261116" author="your-name" context="mysql,postgresql">
  <preConditions onFail="MARK_RAN">
    <not><tableExists tableName="hs_dm_mixing_plan"/></not>
  </preConditions>
  <createTable tableName="hs_dm_mixing_plan" remarks="配比方案">
    <column name="id" type="BIGINT" remarks="主键ID">
      <constraints primaryKey="true" nullable="false"/>
    </column>
    <column name="plan_code" type="VARCHAR(16)" remarks="方案业务编号">
      <constraints nullable="false"/>
    </column>
    <!-- ... -->
  </createTable>
  <createIndex tableName="hs_dm_mixing_plan" indexName="idx_dm_plan_code">
    <column name="plan_code"/>
  </createIndex>
</changeSet>
```

【强制】

1. `id` 全项目唯一：`{业务}-{动作}-{对象}-{yyyyMMdd}`；已执行 changeSet 禁止修改，变更新增 changeSet。
2. 每个 changeSet 必须有 `preConditions onFail="MARK_RAN"`：建表 `not tableExists`、加列 `not columnExists`、初始化数据 `sqlCheck expectedResult=0`。
3. 只操作本模块表；禁止改平台 `sys_*` 表或其他模块表。
4. 字典/菜单初始化与业务表分开文件、分开 changeSet。
5. `spring.liquibase.enabled` 默认 `false`，测试/生产首次部署显式开启；执行前备份数据库。
6. 生产禁止修改历史 changeSet checksum；需要修复时新增 changeSet 或 `changelogSync`。

### 4.5 字典

| 字典类型 | 用途 | 项 |
| --- | --- | --- |
| `dm_pool_status` | 数据池状态 | `draft` / `enabled` / `disabled` / `failed` |
| `dm_plan_status` | 方案状态 | `draft` / `enabled` / `disabled` |
| `dm_task_status` | 任务状态 | `pending` / `running` / `stopping` / `completed` / `partial_failed` / `failed` / `stopped` |
| `dm_result_status` | 结果状态 | `generating` / `available` / `failed` / `expired` |
| `dm_dataset_status` | 数据集状态 | `draft` / `published` / `archived` |
| `dm_source_type` | 数据来源 | `upload` / `asc` / `ltp` / `dataset` |
| `dm_dedup_policy` | 去重策略 | `none` / `exact_hash` / `semantic` |
| `dm_ratio_mode` | 比例模式 | `percent`（一期只支持百分比） |

【强制】字典来源/类型/项号段向平台申请；前端通过字典加载，不写死中文与 alias 的映射（纯前端展示映射可保留常量，但值必须与后端一致）。

### 4.6 业务编号

格式：前缀（2–4 位大写）+ `yyMMdd` + 6 位安全随机码；字符集 `23456789ABCDEFGHJKMNPQRSTUVWXYZ`（去掉 0/O、1/I/L），使用 `SecureRandom`。

| 对象 | 前缀 | 示例 |
| --- | --- | --- |
| 数据池 | `POOL` | `POOL261116A3F9KX` |
| 配比方案 | `PLAN` | `PLAN261116K7M2PQ` |
| 配比任务 | `MTK` | `MTK261116H2N4RT` |
| 配比结果 | `MIX` | `MIX261116Q8W3YZ` |
| 数据集版本 | `MDS` | `MDS261116B5D7FG` |

【强制】

1. 编号生成集中在一个 `DmBizCodeGenerator`，业务代码不拼接。
2. 前缀可配置；对外发布后冻结。
3. 唯一约束冲突时自动重试（最多 3 次），不把异常抛给用户。
4. 对外 URL/分享用业务编号，不用雪花 ID；雪花 ID 不暴露在 URL。

### 4.7 数据迁移、备份与回滚

【强制】

1. 首次部署前备份目标库；Liquibase 脚本不写 rollback 时，回滚只能靠备份。
2. 大表变更（加列/改类型/回填）拆成多步：加可空列 → 双写/回填 → 加约束 → 删旧列；每步可独立回滚。
3. 回填脚本分批（每批 1000–5000），避免长事务与锁表。
4. 发布后核对 `DATABASECHANGELOG` 与关键表行数。
5. 测试环境可重建；生产禁止 `drop table`。

### 4.8 多副本

【强制】

1. 雪花 `hsmty.id.worker-id` 每实例不同（1–31），`datacenter-id` 按机房配置。
2. 定时任务/轮询任务多副本时只开一个（配置开关或分布式锁）。
3. 任务恢复扫描用数据库行锁/分布式锁，避免多实例重复处理。
4. 本地缓存与文件存储不能假设单实例；共享状态放 Redis/DB/对象存储。

---

## 5. 接口契约规范

### 5.1 统一返回

```json
{
  "code": "0000",
  "message": "SUCCESS",
  "data": {},
  "param": null
}
```

- 成功 `code="0000"`；失败为平台错误码（如 `C9999`）。
- 前端统一按 `code !== "0000"` 处理；拦截器自动提示并 reject。
- 无数据成功 `data=null`。

### 5.2 分页

请求：`page`（默认 1）、`limit`（默认 10）。

响应：

```json
{
  "current": 1,
  "limit": 10,
  "totalPage": 3,
  "total": 25,
  "rows": []
}
```

### 5.3 类型约定

| 类型 | 约定 |
| --- | --- |
| 主键/外键 | 后端 `Long` 雪花；JSON 序列化为 **string**，前端按 string |
| 时间 | `yyyy-MM-dd HH:mm:ss`（GMT+8） |
| 空值 | 后端 `null`；前端展示 `—` |
| 比例/分值 | `number`，比例 3 位小数，分值 1 位小数 |
| 枚举 | 小写英文 alias；中文只在前端展示 |
| 布尔 | API `true/false`；DB `T/F` |
| 文件大小 | 字节 `fileSize`；展示用 `sizeMb`（1 位小数） |
| 任务阶段 | `stage` 可选，小写蛇形；前端可只展示 `currentStep` |

### 5.4 路径与权限

- 完整路径 = `/hs-api` + `/dm` + Controller `@RequestMapping` + 方法路径。
- 权限码：`dm:{资源}:{动作}`；动作固定 `page/detail/create/update/remove`，业务动作 `status/import/export/start/stop/retry/publish/copy/download/option`。
- 权限码必须在三处一致：Controller `@PreAuthorize`、UAP 菜单 `permissions`、前端 `can()`。

### 5.5 契约文件

```text
contract/
├── VERSION                 # contractVersion、算法基线
├── README.md               # 文件说明、变更流程、铁律
├── api-contract.md         # 接口、字段、分页、状态、缺口
├── enums.md                # 状态、权限码、字典、编号前缀
├── auth.md                 # SSO Cookie、302、服务间鉴权
├── algorithm-integration.md# 算法请求/响应/轮询/错误/配置
├── deployment-checklist.md # 部署前确认、冒烟、回滚
├── openapi.json            # 后端导出，不手改
├── SYNC.md                 # 当前状态、阻塞、下一步
└── decisions/ADR-*.md      # 架构决策
```

【强制】

1. 契约是唯一源；代码不是契约。
2. `openapi.json` 只能从 `/hs-api/v3/api-docs/dm` 导出，禁止手改。
3. 契约不写 Cookie、Token、密钥、内网密码。
4. 未实现接口标 `planned`/`partial`，不能装作可用。
5. 破坏性变更（删字段/改名/类型变化）升 minor，写变更记录并通知所有会话。
6. 每个域开工前重读 `VERSION`、`SYNC.md`、`api-contract.md`。

### 5.6 错误码

【推荐】

1. 通用错误用平台 `CommonResponseEnum`（参数错误、对象不存在、无权限、重复操作等）。
2. 模块特有错误定义 `DmResponseEnum`，错误码段向平台申请，不与其他模块冲突。
3. 错误消息包含可操作信息，例如：
   - `配比方案至少需要 2 个组分`
   - `组分比例合计必须为 100，当前为 99.5`
   - `数据池【xxx】可用记录不足：需要 1000，实际 800`
   - `任务已在运行，请勿重复启动`
4. 算法原始错误码只记日志，不直接透传；映射为业务错误或“算法服务暂不可用”。

### 5.7 幂等键

【强制】异步创建/启动接口支持：

```http
Idempotency-Key: MTK261116H2N4RT
```

- 服务端用 Redis 记录 `dm:idem:{key}` → 首次响应，TTL 24h。
- 重复请求返回首次结果；如果首次仍在处理，返回“处理中”。
- key 由前端用业务编号或 UUID 生成；同一用户同一操作复用。

### 5.8 接口状态标注

在 `api-contract.md` 每个接口表加“状态”列：

| 状态 | 含义 |
| --- | --- |
| `implemented` | 后端已实现且 OpenAPI 可验证 |
| `partial` | 部分实现，字段可能调整 |
| `planned` | 已定方向，未实现 |

---

## 6. 异步任务与状态机

### 6.1 何时异步

以下操作必须异步，接口只返回任务 ID：

1. 大文件导入/解析/统计（>10 万条或 >10MB）。
2. 配比抽样、去重、质量过滤、文件生成。
3. 调用算法服务的耗时任务。
4. 批量导出/报告生成。

轻量 CRUD、选项查询、单条详情保持同步。

### 6.2 任务表模板

```sql
CREATE TABLE hs_dm_task (
  id             BIGINT       NOT NULL COMMENT '主键ID',
  task_no        VARCHAR(32)  NOT NULL COMMENT '任务编号',
  biz_type       VARCHAR(30)  NOT NULL COMMENT '业务类型：pool_import/pool_stat/mixing/quality',
  biz_id         BIGINT       NOT NULL COMMENT '业务对象ID',
  status         VARCHAR(20)  NOT NULL COMMENT 'pending/running/success/failed/stopped',
  progress       INT          NOT NULL DEFAULT 0 COMMENT '进度0-100',
  current_step   VARCHAR(100) NULL COMMENT '当前步骤',
  retry_count    INT          NOT NULL DEFAULT 0 COMMENT '重试次数',
  error_message  VARCHAR(1000) NULL COMMENT '失败原因',
  start_time     DATETIME     NULL COMMENT '开始时间',
  finish_time    DATETIME     NULL COMMENT '结束时间',
  heartbeat_time DATETIME     NULL COMMENT '心跳时间',
  create_id      BIGINT       NULL,
  create_time    DATETIME     NULL,
  update_id      BIGINT       NULL,
  update_time    DATETIME     NULL,
  del_flag       CHAR(1)      NOT NULL DEFAULT 'F',
  PRIMARY KEY (id),
  KEY idx_dm_task_biz (biz_type, biz_id),
  KEY idx_dm_task_status (status, heartbeat_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='异步任务';
```

> 业务表（如 `hs_dm_mixing_task`）是用户可见状态权威；`hs_dm_task` 是执行记录。两者通过 `biz_type/biz_id` 关联，状态映射必须写清楚。

### 6.3 通用任务状态机

```text
pending → running → success
                  ├→ failed
                  └→ stopped
running → stopping → stopped
failed/stopped → pending（重试）
```

【强制】

1. 只允许表中迁移；非法迁移返回“当前状态不允许该操作”。
2. 终态：`success/failed/stopped`；终态不再自动变化。
3. 停止是“请求停止”，先置 `stopping`，执行器检查中断标志后置 `stopped`；不要直接跳过 `stopping`。
4. 重试创建新任务或重置原任务，必须保留 `retry_count` 与历史错误。

### 6.4 提交与执行

```java
// 事务提交后再投递，避免异步线程读不到未提交数据
TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
    @Override
    public void afterCommit() {
        taskExecutor.submit(taskNo, () -> mixingRunner.run(taskId));
    }
});
```

执行器：

```java
@Component
public class DmTaskExecutor implements DisposableBean {
    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
    private final Semaphore permits;

    public void submit(String taskNo, Runnable task) {
        executor.execute(() -> {
            boolean acquired = false;
            try {
                permits.acquire();
                acquired = true;
                task.run();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                log.warn("任务被中断: {}", taskNo);
            } catch (Throwable e) {
                log.error("任务执行异常: {}", taskNo, e);
            } finally {
                if (acquired) permits.release();
            }
        });
    }
}
```

【强制】

1. 全局并发上限 `dm.task.max-concurrent`，超出排队，不阻塞 HTTP 线程。
2. 每 30 秒更新 `heartbeat_time` 与 `progress`。
3. 长循环检查 `Thread.currentThread().isInterrupted()` 或任务停止标志。
4. 任务开始时把业务对象置 `running`，结束时按结果置终态；异常必须落 `error_message`。

### 6.5 残留任务恢复

```text
每 5 分钟扫描：
  status='running' AND heartbeat_time < now - 2min
  → 若本实例无该任务：置 failed，原因“服务重启导致任务中断”
  → 业务对象同步置 failed，允许重跑
```

【强制】

1. 恢复任务必须幂等；多副本用数据库行锁/Redis 锁。
2. 恢复后清理临时文件与半成品结果。
3. 日志记录任务号、最后心跳、恢复动作。

### 6.6 停止与竞态（重点）

错误写法：

```java
experiment.setStatus("stopped");
updateById(experiment);
// 另一个线程随后把 completed 写回，停止被覆盖
```

正确写法：

```java
Object lock = lockOf(taskId);
synchronized (lock) {
    MixingTaskEntity latest = getById(taskId);
    if (!RUNNING.equals(latest.getStatus())) {
        throw new BizException("任务已结束，无法停止");
    }
    // 置 stopping，通知执行器
    updateStatus(taskId, RUNNING, STOPPING);
}
// 执行器在落最终结果前，再次在锁内读取状态：
synchronized (lock) {
    MixingTaskEntity latest = getById(taskId);
    if (!RUNNING.equals(latest.getStatus())) {
        return; // 已被停止，不写 completed
    }
    persistResult();
    updateStatus(taskId, RUNNING, COMPLETED);
}
```

【强制】

1. 停止与完成/失败落库必须互斥（按 ID 分桶锁或分布式锁）。
2. 落库前重新读取状态；状态不是 `running` 就放弃写入。
3. `stop()` 接口在锁内重新读取；如果已完成，返回“任务已结束，无法停止”，不要假装成功。
4. 写专项测试：运行中停止、完成前 5 秒停止、停止后重跑。

### 6.7 进度

| 阶段 | progress | currentStep |
| --- | --- | --- |
| 提交 | 0 | 排队中 |
| 准备 | 5 | 校验方案与数据池 |
| 过滤/去重 | 20 | 过滤与去重 |
| 抽样 | 20–60 | 按组分抽样 |
| 合并/写文件 | 60–85 | 生成数据集文件 |
| 质量统计 | 85–95 | 统计实际比例与质量 |
| 完成 | 100 | 已完成 |

前端 2 秒轮询 `/task/{id}/progress`，终态停止；最长 2 分钟提示“处理中，稍后刷新”。

### 6.8 失败分类与重试

| 类型 | 例子 | 处理 |
| --- | --- | --- |
| 业务错误 | 方案比例不等于 100、数据池停用、记录不足 | 不重试，直接 failed，提示用户修正 |
| 基础设施错误 | 算法超时/5xx、存储不可用、网络抖动 | 可重试 2–3 次，指数退避；仍失败则 failed |
| 数据错误 | 文件损坏、编码错误、记录解析失败 | 标记失败行/文件，按策略跳过或整体失败 |
| 用户停止 | 手动停止 | stopped，不重试 |

【强制】重试只重试幂等步骤；已写出的半成品先清理或覆盖。

---

## 7. 算法服务集成

### 7.1 边界

| 谁负责 | 内容 |
| --- | --- |
| DM 后端 | 用户、权限、方案/任务状态机、输入快照、结果落库、页面 |
| 算法服务 | 抽样、去重、质量检查、文件生成、统计 |
| 前端 | 不直连算法；只调用 DM 后端 |

【强制】不把算法产物复制进业务库；业务库只存 `jobId`、摘要、版本、产物 URI、哈希。

### 7.2 配置

```yaml
dm:
  algorithm:
    enabled: true
    base-url: "http://192.168.1.105:17029/algorithm/v1"
    internal-token: ${DM_ALGORITHM_INTERNAL_TOKEN:}
    connect-timeout: 3s
    read-timeout: 10s
    upload-timeout: 10m
    poll-interval: 2s
    poll-timeout: 30m
    storage-mode: file
```

【强制】

1. 非密钥地址、超时、开关可直接写明，便于甲方阅读。
2. 令牌只从环境变量/配置中心注入；如果算法侧已关闭校验，留空，不要伪造。
3. 配置项用 `@ConfigurationProperties` 绑定，提供默认值；禁止散落 `@Value`。
4. 算法服务必须有 `GET /health`，DM 启动/任务前检查；健康失败给出明确提示。

### 7.3 文件传递方式

| 模式 | 做法 | 适用 | 约束 |
| --- | --- | --- | --- |
| `file`【推荐】 | DM 先 `POST /files` 上传，拿 `fileId`，再提交任务 | 无共享存储、跨容器 | 算法必须提供上传接口；文件 ID 有生命周期 |
| `local` | 传文件路径，双方挂同一持久卷 | 同机/同 Pod | 路径必须一致；多副本需共享存储 |
| `oss` | 传预签名 URL / object key | 对象存储 | 算法需能访问 OSS；密钥不落库 |

【强制】

1. 默认 `file` 模式；不要依赖“双方恰好有同一个目录”。
2. 共享存储不是“网络连通”就够了：必须是同一挂载点、同一路径、同一权限。
3. 文件上传做流式，不把 1GB 文件读进内存；上传超时单独配置。
4. 文件 ID/路径缓存按 `contentHash`，避免重复上传；缓存要能失效。
5. 算法返回的文件 URI 只存引用；下载走 DM 后端或预签名，不暴露算法内网地址。

### 7.4 请求 / 响应 / 错误

提交任务：

```json
POST /mixing/jobs
{
  "requestId": "MTK261116H2N4RT",
  "planVersion": 3,
  "seed": "A1B2C3D4",
  "targetTotal": 10000,
  "components": [
    {
      "componentId": "1",
      "fileId": "file_abc",
      "ratio": 60.000,
      "qualityThreshold": 0.8,
      "dedupPolicy": "exact_hash"
    }
  ],
  "options": { "dedupBeforeSample": true }
}
```

响应：

```json
{ "jobId": "job_123", "status": "queued" }
```

查询：

```json
GET /jobs/job_123
{
  "jobId": "job_123",
  "status": "running",
  "stage": "sampling",
  "progress": 45,
  "message": "正在抽样",
  "result": null,
  "error": null
}
```

错误：

```json
{
  "success": false,
  "code": "INVALID_PARAMETER",
  "message": "ratio sum must be 100",
  "retryable": false,
  "traceId": "trace-xxx",
  "details": {}
}
```

【强制】

1. 请求/响应字段显式 schema，不用自由 JSON；新增字段兼容，删改字段升版本。
2. 错误解析兼容顶层与 `detail` 包裹两种形态（LTP V2.0/V2.1 经验）。
3. `retryable=true` 才自动重试；`false` 直接失败。
4. 记录 `traceId` 到日志，不透传给前端。
5. 幂等：提交带 `requestId`/`Idempotency-Key`，算法重复请求返回同一 `jobId`。

### 7.5 轮询、超时、取消

| 项 | 约定 |
| --- | --- |
| 轮询间隔 | 2s；超过 5 分钟转 5s |
| 总超时 | 30 分钟；超过只转慢轮询并标“状态未知”，不直接判失败 |
| 连接超时 | 3s |
| 普通读超时 | 10s |
| 上传超时 | 10 分钟 |
| 取消 | `POST /jobs/{id}/cancel`；业务侧先置 `stopping` |
| 心跳 | 算法 `updatedAt` 超过 2 分钟未变，标“状态未知”并告警 |

### 7.6 状态映射

| 算法状态 | DM 任务 | DM 业务对象 |
| --- | --- | --- |
| `queued` | `pending` | `pending` |
| `running` | `running` | `running` |
| `succeeded` | `success` | `completed`（结果落库后） |
| `failed` | `failed` | `failed` |
| `cancelled` | `stopped` | `stopped` |

【强制】业务状态是权威；算法状态只用于推进业务状态，前端不展示上游原值。

### 7.7 网关抽象与降级

```java
public interface MixingGateway {
    SubmitResult submit(MixingRequest request);
    JobStatus query(String jobId);
    void cancel(String jobId);
}
```

实现：

- `AlgorithmMixingGateway`：真实算法。
- `LocalMixingGateway`：本地抽样/去重，算法不可用时兜底（仅限非关键能力）。
- `NoopMixingGateway`：算法未接入时明确失败，不伪造成功。

【强制】

1. 通过配置/profile 切换实现，不把 `if (algorithmEnabled)` 散落在业务代码。
2. 降级只用于“可降级能力”（如预览、统计）；配比结果生成不应静默降级。
3. Noop 实现返回明确错误，任务落 `failed`，不要停在 `running`。

### 7.8 安全与日志

【强制】

1. 算法地址、令牌只在后端配置；前端不可见。
2. 只记录 `jobId`、阶段、耗时、错误码；不记录请求体、文件内容、令牌。
3. 算法返回的错误消息截断 500 字，避免日志爆炸。
4. 生产环境算法服务走内网/网关，不暴露公网。

### 7.9 联调步骤

1. `GET /health`：`status=up`、`storage=up`、`modelService`（如有）。
2. 上传一个小文件 → 拿 `fileId` → 提交任务 → 轮询到 `succeeded`。
3. 校验结果文件条数、哈希、目标/实际比例。
4. 取消一个运行中任务 → DM `stopped`。
5. 停掉算法 → 提交任务 → DM 明确失败/可重试，不悬挂。
6. 算法版本升级 → 重跑同 seed → 结果可复现或明确记录算法版本差异。

### 7.10 算法版本变更

【强制】算法每次不兼容变更必须：

1. 更新 `contract/algorithm-integration.md` 与 `contract/VERSION`。
2. 提供变更说明（字段、状态、错误码、文件接口）。
3. DM 后端适配后先本地联调，再推测试环境。
4. 记录基线版本，历史任务保留算法版本，不重算。

---

## 8. 前端开发规范

### 8.1 模块注册

```ts
import { defineModule } from '@/core';
import './styles/index.scss';

export const DmModule = defineModule({
  name: 'dm',
  title: '数据配比',
  icon: 'DataAnalysis',
  components: {
    '/dm/pool/index': {
      component: () => import('./views/pool/index.vue'),
      title: '数据池管理',
      sort: 1,
      breadcrumb: [{ pageName: '数据池管理' }],
      pageTip: '管理参与配比的数据池，查看来源、规模与质量。'
    },
    '/dm/plan/index': {
      component: () => import('./views/plan/index.vue'),
      title: '配比方案',
      sort: 2,
      breadcrumb: [{ pageName: '配比方案' }],
      pageTip: '配置数据池、目标比例、质量阈值与去重策略。'
    },
    '/dm/task/index': {
      component: () => import('./views/task/index.vue'),
      title: '配比任务',
      sort: 3,
      breadcrumb: [{ pageName: '配比任务' }],
      pageTip: '按方案快照执行配比，查看进度、停止与重跑。'
    },
    '/dm/result/index': {
      component: () => import('./views/result/index.vue'),
      title: '配比结果',
      sort: 4,
      breadcrumb: [{ pageName: '配比结果' }],
      pageTip: '查看目标/实际比例、质量报告，发布为数据集版本。'
    },
    '/dm/result/detail/index': {
      component: () => import('./views/result/detail/index.vue'),
      title: '配比结果详情',
      isHidden: 'T',
      breadcrumb: [{ pageName: '配比结果', path: '/dm/result/index' }, { pageName: '详情' }]
    }
  }
});
```

【强制】

1. `name` 是路由前缀，全局唯一：`dm`。
2. `components` key 必须与 UAP 菜单 `component`、物理路径一致。
3. 详情页 `isHidden: 'T'`，路由可直达但不显示菜单。
4. 模块只注册自己的页面；不修改 `src/router`、`src/core` 等公共文件（需要改走 PR 评审）。

### 8.2 前端目录

```text
src/modules/dm/
├── register.ts
├── api/
│   ├── http.ts          # createModuleHttp('dm', '/hs-api/dm')
│   ├── pool.ts
│   ├── plan.ts
│   ├── task.ts
│   ├── result.ts
│   └── dataset.ts
├── types/
│   ├── common.ts
│   ├── pool.ts
│   ├── plan.ts
│   ├── task.ts
│   └── result.ts
├── constants/
│   ├── enums.ts
│   └── options.ts
├── utils/
│   ├── format.ts
│   └── permission.ts
├── styles/index.scss
└── views/
    ├── pool/index.vue
    ├── plan/index.vue
    ├── task/index.vue
    ├── result/index.vue
    └── result/detail/index.vue
```

### 8.3 API 层

```ts
// api/http.ts
import { createModuleHttp } from '@/api/client';
export const dmHttp = createModuleHttp('dm', '/hs-api/dm');

// api/plan.ts
import { dmHttp } from './http';
import type { IPage, PlanCreateForm, PlanQuery, PlanVO } from '../types';

export const planPageApi = (params: PlanQuery): Promise<IPage<PlanVO>> =>
  dmHttp.get<IPage<PlanVO>>('/plan', params);

export const planCreateApi = (data: PlanCreateForm): Promise<void> =>
  dmHttp.post('/plan', data);
```

【强制】

1. 所有请求集中在 `api/`；页面不直接写 `axios`/`fetch`。
2. `apiPrefix` 是完整后端路径 `/hs-api/dm`；dev 走 Vite 代理，生产走 nginx 同源。
3. 请求函数显式标注参数与返回类型。
4. 分页类型 `IPage<T>` 与后端 `current/limit/totalPage/total/rows` 对齐。
5. 长 ID 一律 `string`；不要 `Number(id)`。

### 8.4 类型

```ts
export type PlanStatus = 'draft' | 'enabled' | 'disabled';

export interface PlanComponent {
  poolId: string;
  ratio: number;          // 0-100，3 位小数
  qualityThreshold?: number;
  dedupPolicy?: 'none' | 'exact_hash' | 'semantic';
}

export interface PlanVO {
  id: string;
  planCode: string;
  name: string;
  status: PlanStatus;
  versionNo: number;
  components: PlanComponent[];
  createTime: string;
}
```

【强制】

1. 类型与契约字段一一对应；不使用 `any` 承接接口响应。
2. 枚举用联合类型 + `as const` 选项；业务枚举优先从字典加载。
3. 可选字段用 `?`；空值展示统一 `emptyText`（`—`）。

### 8.5 页面结构

#### 列表页（固定顺序）

1. 页面 Banner：标题 + 一句话说明（由基座根据 `pageTip` 渲染，不在页面重复写）。
2. 搜索卡：label + 控件横排，字段间距 16px，按钮右对齐 `[重置] [主按钮] [刷新]`。
3. 表格卡：标题 + 右侧操作；ProTable。
4. 分页：右下。

#### 新增/编辑

| 字段量 | 载体 |
| --- | --- |
| ≤ 8 个短字段 | 弹窗 640px |
| 9–15 个字段 | 弹窗 720px 或抽屉 |
| > 15 个字段 / 含明细行 / 需要对照列表 | 抽屉（72% 详情，86% 工作台） |
| 极复杂 / 需要 URL / 多步流程 | 独立页面 |

【强制】

1. 详情一律抽屉，不用弹窗堆详情。
2. 弹窗里禁止再套弹窗；二级内容用抽屉/页面。
3. 弹窗底部按钮右对齐 `[取消] [确定]`；表单 label 100px 右对齐；控件 32px。
4. 弹窗最大高度 88vh，header/footer 固定，body 独立滚动（LTP 保存按钮不可点事故）。
5. 编辑必须回填原值；标题随动作变化“新增/修改”。

#### 配比方案编辑器（DM 特有）

- 使用 86% 抽屉。
- 组分表格：数据池、比例、质量阈值、去重策略、删除；支持添加/排序。
- 顶部实时显示“比例合计 100.000%”；不等于 100 时禁用保存并标红。
- 至少 2 个组分，最多 `dm.mixing.max-component`（前端从配置接口或常量读取，避免硬编码）。
- 目标总量、随机种子（可选）、是否允许不足（默认不允许）。
- 保存前二次确认；保存后生成方案版本。

### 8.6 ProTable

```vue
<ProTable
  ref="proTableRef"
  title="配比方案"
  :columns="columns"
  :search-columns="searchColumns"
  :request-api="getTableList"
  :tool-button="false"
  row-key="id"
  :row-style="{ height: '44px' }"
>
  <template #tableHeader>
    <div class="dm-table-header">
      <span class="dm-table-title">配比方案</span>
      <el-button v-if="can('dm:plan:create')" type="primary" :icon="CirclePlus" @click="openCreate">
        新建方案
      </el-button>
    </div>
  </template>
</ProTable>
```

【强制】

1. 列表页优先 ProTable（分页/搜索/操作列/列设置）；详情内小列表可用 `el-table`。
2. 操作列固定最右，文字按钮，间距 12px。
3. 主字段第一列加粗；空值 `—`；编号/版本 monospace。
4. 表格无斑马纹；列头 40px；行高 44px。

### 8.7 弹窗 / 抽屉

- 弹窗宽 640/720px，圆角 8px，遮罩 `rgba(0,0,0,.45)`。
- 抽屉右侧滑出，详情 72%，工作台 86%，阴影 `-8px 0 24px rgba(15,23,42,.12)`。
- 抽屉结构：头部（标题 + 状态 + meta）→ Tabs（可选）→ 浅灰内容区白卡 → 固定底部操作。
- 详情只读；编辑通过底部“编辑”打开弹窗/抽屉。

### 8.8 权限

```ts
import { can } from '../../utils/permission';

<el-button v-if="can('dm:plan:create')" ...>新建方案</el-button>
```

```ts
import { qiankunWindow } from 'vite-plugin-qiankun/dist/helper';
import { getPermission } from '@/utils/qiankun/handleGlobalState';

export const can = (code: string): boolean => {
  if (!qiankunWindow.__POWERED_BY_QIANKUN__) return true;
  try { return getPermission(code); } catch { return false; }
};
```

【强制】

1. 权限码与契约一致，不在页面硬编码业务值。
2. 页面入口 + 按钮都要控制；后端仍然必须校验，前端隐藏不是安全边界。
3. 独立运行（本地壳）放行仅用于开发；提测/生产必须走 UAP。

### 8.9 轮询

```ts
const timer = window.setInterval(async () => {
  const data = await taskProgressApi(taskId);
  if (['completed', 'partial_failed', 'failed', 'stopped'].includes(data.status)) {
    window.clearInterval(timer);
    await refresh();
  }
}, 2000);

onUnmounted(() => window.clearInterval(timer));
```

【强制】

1. 2 秒轮询；终态停止；最长 2 分钟提示“处理中，稍后刷新”。
2. 组件卸载清理定时器。
3. 页面隐藏（`document.hidden`）时暂停轮询，回到前台再恢复。
4. 不要用 `setInterval` 嵌套请求导致堆积；上次未返回则跳过本次。

### 8.10 错误与登录失效

【强制】

1. 统一走基座 HTTP 封装；非 `0000` 自动提示并 reject。
2. 识别 302/HTML 登录页：`response.headers['content-type']` 含 `text/html` 或 `response.status===302` 时，跳转平台登录，不把 HTML 当 JSON 解析。
3. 网络错误给出“网络异常，请稍后重试”；不要吞错。
4. 401/403/302 处理与基座其他模块一致，不单独造轮子。

### 8.11 UI Token 与样式

【强制】

1. 主色 `#4169f6` 锁死；成功 `#12b76a`；危险 `#f04438`；警示 `#b45309`。
2. 白卡、1px `#e4edf8` 边、8px 圆角、无阴影、padding 18px 20px。
3. 按钮三档：L 40px / M 32px（默认）/ S 26px；同一区域统一；一个区域一个主按钮。
4. 表格列头 `#f4f6fb`、12px/700/`#7a8493`、40px；行高 44px；无斑马纹。
5. 状态徽标胶囊 22px；成功绿/危险红/警示橙/信息蓝/中性灰。
6. 空值 `—`；时间 `YYYY-MM-DD HH:mm:ss`；编号 monospace 12px。
7. 业务样式作用域 `.dm-page` / `.dm-dialog` / `.dm-drawer`，不覆盖全局 Element Plus。
8. 禁止深色侧边栏、大面积渐变、圆角 >10px、重阴影、彩虹图表。

### 8.12 构建与质量

```bash
pnpm type-check
pnpm lint
pnpm build
```

【强制】

1. 提交前 `type-check` 通过；构建失败不提交。
2. 不修改公共层（`src/components`、`src/core`、`src/router`、`src/styles`）除非 PR 评审通过。
3. 不新增依赖除非评审；不提交 `dist/`、`node_modules/`。
4. 组件 `defineOptions({ name: 'DmXxxView' })` 全局唯一。

### 8.13 前端验收

| 项 | 标准 |
| --- | --- |
| 菜单 | 5 个页面可见，详情页不显示 |
| 权限 | 无权限账号看不到按钮，接口 403 |
| 列表 | 搜索/重置/分页/排序/空态正常 |
| 表单 | 必填/长度/比例和校验，错误提示可读 |
| 抽屉 | 详情只读，底部固定，内容滚动 |
| 轮询 | 进度更新，终态停止，卸载清理 |
| 兼容 | 1280px 最小宽度；表格横向滚动 |
| 构建 | `pnpm build` 成功，dist 可部署 |

---

## 9. 权限、菜单与 UAP

### 9.1 权限模型

平台权限由 UAP 管理，业务模块只声明权限码并校验。核心表：

| 表 | 用途 |
| --- | --- |
| `t_uap_authority` | 菜单/按钮（树） |
| `t_uap_resource` | 接口资源（权限码） |
| `t_uap_authority_resource` | 菜单-资源关联 |
| `t_uap_role_authority` | 角色-菜单 |
| `t_uap_role_resource` | 角色-资源 |

### 9.2 权限码设计

```text
dm:dashboard:page
dm:pool:page/detail/create/update/remove/status/import/option
dm:plan:page/detail/create/update/remove/status/publish/copy/option
dm:task:page/detail/create/start/stop/retry/remove
dm:result:page/detail/download/publish/expire
dm:dataset:page/detail/create/update/remove/publish/archive/version
dm:config:page/update
```

【强制】

1. 权限码与 `@PreAuthorize`、UAP 资源 `code/value`、菜单 `permissions` 完全一致。
2. 页面权限码控制能否进入页面；按钮权限码控制操作。
3. 一个接口至少一个权限码；不要用“登录即可”代替权限。
4. 新增/删除权限码必须同步契约、UAP 清单、前端 `can()`。

### 9.3 菜单与组件一致性

| 层 | 值 |
| --- | --- |
| UAP 菜单 `component` | `/dm/plan/index` |
| `register.ts` key | `/dm/plan/index` |
| 物理文件 | `src/modules/dm/views/plan/index.vue` |

【强制】三处必须完全一致；不一致会导致“路由能进但白屏/菜单丢失”。

### 9.4 UAP 接口

| 操作 | 接口 |
| --- | --- |
| 菜单树 | `GET /uap-manager/auth/allTree` |
| 保存菜单 | `POST /uap-manager/auth/save` |
| 角色已选菜单 | `GET /uap-manager/auth/selectedTree?roleId=` |
| 菜单关联资源 | `POST /uap-manager/auth/saveWithResource`（multipart：`authId` + 单个逗号分隔 `resourceIds`） |
| 角色授权资源 | `POST /uap-manager/auth/saveWithResourceToRole`（multipart：`roleId`、`authId` + 单个逗号分隔 `resourceIds`） |
| 角色菜单授权 | `POST /uap-manager/role/disAuth`（multipart：`roleId` + 单个逗号分隔 `authIds`） |
| 保存资源 | `POST /uap-manager/resource/save` |
| 资源查询 | `GET /uap-manager/resource/list?pageNum=1&pageSize=50&resourceName=` |
| 角色列表 | `GET /uap-manager/role/list` |

【强制】

1. `resource/save` 的 `code` 与 `value` 都填权限码，`operation` 填数字字符串；不要依赖自动生成数字 code。
2. multipart 的 `resourceIds`/`authIds` 必须是**一个逗号分隔字符串**，不是多个同名字段（LTP/ASC 踩坑）。
3. 角色菜单选择是单独的 `role/disAuth`，只做菜单-资源关联不会让菜单出现在 `selectedTree`。
4. 批量导入前先 dry-run，输出将创建/复用/修正的清单；确认后 `--execute`。
5. Cookie 只放环境变量 `UAP_COOKIE`，不写文件、不提交、不打日志。
6. 导入后重新登录，检查 `permissions/verify` 返回 `dm:*`，以及 `auth/selectedTree` 菜单勾选。

### 9.5 批量导入流程

```text
1. 写 docs/UAP权限注册清单-DM.md（菜单、权限码、关联、角色）
2. 写 tools/uap/import_dm.py（解析文档、dry-run、--execute）
3. 预检：父菜单存在、无重复 URL、无重复权限码、资源 code 正确
4. 创建/修正资源（resource/save）
5. 创建菜单（auth/save），父级按层级
6. 菜单-资源关联（auth/saveWithResource）
7. 角色菜单授权（role/disAuth，保留已有菜单）
8. 角色资源授权（auth/saveWithResourceToRole）
9. 后置检查：auth/selectedTree、permissions/verify、重复资源
10. 清理重复/错误资源（先确认无引用）
```

### 9.6 常见坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 菜单不显示 | 角色未 `role/disAuth` | 补角色菜单授权 |
| 菜单显示白屏 | `component` 与 `register.ts` 不一致 | 三处对齐 |
| 接口 403 | 权限码未挂角色/未重新登录 | 补资源授权，刷新会话 |
| 资源 code 是数字 | `resource/save` 未传 `code/value` | 重新保存并核对 `resource/info` |
| `saveWithResourceToRole` 报必填为空 | 多个同名字段 | 改单个逗号分隔字符串 |
| 重复资源 | 手工多次创建 | 查 `resource/list`，清理无引用重复项 |

---

## 10. 测试与验收

### 10.1 测试分层

| 层 | 范围 | 工具 | 何时 |
| --- | --- | --- | --- |
| 单元测试 | 比例计算、状态迁移、校验、编号 | JUnit 5 + AssertJ | 每次提交 |
| 集成测试 | 启动、DB、Redis、Liquibase | `@SpringBootTest` + 测试库 | 每轮提测 |
| 契约测试 | OpenAPI 与前端类型/字段 | 导出 + diff | 接口变更 |
| 边界脚本 | 接口级异常/权限/并发 | Python requests | 每轮提测 |
| 页面验收 | 主流程、权限、空态、轮询 | 手工/Playwright | 提测/UAT |
| 非功能 | 大文件、并发、恢复 | 脚本/压测 | 上线前 |

### 10.2 单测清单

【强制】至少覆盖：

1. 比例和 = 100 / ≠ 100 / 浮点边界（99.999、100.001）。
2. 组分 < 2 / > max / 重复数据池。
3. 目标总量边界（0、负数、超过 max、小于组分数）。
4. 数据池停用/为空/记录不足。
5. 去重策略：无、精确哈希、语义（mock）。
6. 抽样分配：最大余数法、总量守恒、上限截断。
7. 状态迁移：合法/非法；停止/完成竞态。
8. 幂等：重复启动返回同一任务。
9. 任务恢复：心跳超时置 failed。
10. 业务编号：格式、字符集、冲突重试。

### 10.3 集成测试

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE, properties = {
    "spring.datasource.url=jdbc:h2:mem:dm;MODE=MySQL",
    "spring.liquibase.enabled=true",
    "dm.algorithm.enabled=false"
})
class MixingPlanServiceTest { ... }
```

【强制】

1. 不依赖本地 `application.yml`；用 `properties` 注入最小配置。
2. 测试库可用 H2/Testcontainers；Redis 可用 embedded/mock。
3. 涉及 Liquibase 的用例验证重复启动幂等。
4. 默认 `skipTests=true`，回归显式 `-DskipTests=false` 并确认执行数。

### 10.4 契约测试

1. 后端启动后导出 `openapi.json`。
2. 前端类型与契约字段 diff；缺字段/多字段必须解释。
3. 检查 Long 是否序列化为 string；时间格式；枚举值。
4. 检查 `planned` 接口未被前端调用。

### 10.5 边界脚本

参考 LTP `tools/local-smoke/boundary.py`：

- 只允许 `local-dev` 使用；禁止测试/生产。
- 创建带时间戳的临时数据；默认清理。
- 覆盖：权限、参数、状态、引用保护、重复、并发、停止、恢复。
- 输出通过/失败数与失败详情；退出码非 0 表示失败。

### 10.6 人工验收矩阵

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| DM-01 | 新建数据池并导入 | 状态 enabled，条数/大小正确 |
| DM-02 | 数据池停用 | 新建方案不可选；已有任务不受影响 |
| DM-03 | 新建方案，2 组分 60/40 | 保存成功，版本 v1 |
| DM-04 | 比例 60/30 | 保存失败，提示合计 90 |
| DM-05 | 方案发布后编辑 | 生成新版本，旧版本可查 |
| DM-06 | 按方案创建任务并启动 | 进度更新，最终 completed |
| DM-07 | 运行中停止 | 状态 stopped，结果不生成 |
| DM-08 | 停止后重跑 | 新任务完成，旧结果保留 |
| DM-09 | 数据池记录不足 | 任务 failed，提示需要/实际 |
| DM-10 | 结果详情 | 目标/实际比例、偏差、质量报告正确 |
| DM-11 | 发布数据集版本 | 版本 v1.0，可下载 |
| DM-12 | 无权限账号 | 菜单/按钮不可见，接口 403 |
| DM-13 | 服务重启后任务 | 置 failed，可重跑 |
| DM-14 | 重复点击启动 | 不产生两个运行任务 |

### 10.7 非功能

| 项 | 目标 |
| --- | --- |
| 1GB 文件导入 | 流式，不 OOM；有超时与进度 |
| 100 万条配比 | 任务可完成；内存占用可控；有采样/分批 |
| 并发任务 | 不超过 `max-concurrent`；排队不阻塞接口 |
| 多副本 | 无重复任务/主键冲突 |
| 恢复 | 2 分钟内识别残留任务 |
| 安全 | 无越权下载、无路径穿越、无敏感日志 |

### 10.8 退出标准

- 单测/集成测试通过（显式执行）。
- 边界脚本 100% 通过。
- 前端 `type-check`、`build` 通过。
- 主流程 + 异常流程人工验收通过。
- 无 P0/P1 缺陷；P2 有明确计划。
- 契约、OpenAPI、权限清单、部署清单同步更新。

---

## 11. 部署与上线

### 11.1 组件与端口

| 组件 | 建议端口 | 说明 |
| --- | --- | --- |
| DM 后端 | 8080（容器内） | context `/hs-api`，模块 `/dm` |
| DM 前端 | nginx 静态 | 与基座同源，`/sdom-hsmty/#/dm/...` |
| 算法服务 | 由算法侧提供 | 地址写 `application.yml`，令牌环境变量 |
| MySQL | 由运维提供 | 库名以测试环境为准 |
| Redis | 由运维提供 | 任务锁/幂等/缓存 |

### 11.2 分支策略

| 仓库 | 分支 | 用途 |
| --- | --- | --- |
| 后端 | `master` | 主干，可发布 |
| 后端 | `feature/dm-*` | 功能开发 |
| 后端 | `test`（按需） | 测试环境构建；当前模板只有 `master`，需确认 Jenkins 分支 |
| 前端 | `dev` | 集成 |
| 前端 | `test` | 测试环境 |
| 前端 | `prod` / `master` | 生产 |

【强制】

1. 合并前本地构建通过；数据库变更验证幂等。
2. 前端只覆盖 `src/modules/dm/**` 与必要文档；不修改公共层。
3. 后端提交信息 `{type}(dm): {描述}`；数据库/契约/配置变更在提交说明中标注。
4. 不提交 `target/`、`.idea/`、`logs/`、`data/`、`node_modules/`、`dist/`。

### 11.3 Jenkins

测试环境 Jenkins：`http://192.168.1.110:18080/`。

部署前确认：

1. Job 的源码仓库地址正确。
2. **Branch Specifier** 与要部署的分支一致（前端 `*/test`；后端 `*/master` 或 `*/test`，必须确认后端是否有 `test` 分支）。
3. Node/pnpm/JDK 版本：Node 20.19.5、pnpm 10.x、JDK 21。
4. 构建命令：
   - 后端：`mvn -s settings.xml -pl hsmty-module-dm-core,hsmty-module-dm-start -am clean package -DskipTests`
   - 前端：`pnpm install && pnpm build`
5. 部署步骤：镜像构建/推送 → k8s 滚动更新/nginx 静态替换 → 健康检查。
6. 凭据：Git、镜像仓库、kubeconfig 由 Jenkins Credentials 管理，不写脚本。

构建后：

1. `Console Output` 出现 `BUILD SUCCESS`。
2. 看 Pod/容器状态。
3. 访问测试域名，`Ctrl+F5` 刷新。
4. 后端 `/hs-api/actuator/health` 为 `UP`。
5. 登录后业务接口 `code=0000`。

### 11.4 环境变量

| 变量 | 作用 | 测试环境 |
| --- | --- | --- |
| `SPRING_DATASOURCE_URL/USERNAME/PASSWORD` | 数据库 | 由运维注入；密码 `ENC(...)` 或配置中心 |
| `JASYPT_ENCRYPTOR_PASSWORD` | 解密密码 | **必须换掉默认 `datasource`** |
| `DM_SERVICE_URL` | 本服务对外地址 | `http(s)://<域名>/hs-api` |
| `DM_ALGORITHM_ENABLED` | 算法开关 | `true` |
| `DM_ALGORITHM_BASE_URL` | 算法地址 | 算法侧提供 |
| `DM_ALGORITHM_INTERNAL_TOKEN` | 服务间令牌 | 算法侧要求时注入；关闭则留空 |
| `DM_ALGORITHM_STORAGE_MODE` | 文件模式 | `file` |
| `DM_STORAGE_ROOT` | 本地存储根 | 持久卷路径 |
| `hsmty.verify` / `hsmty.redirect` | 平台登录校验/跳转 | 测试环境 corp 域名 |
| `DM_ALGORITHM_POLL_ENABLED` | 轮询开关 | 多副本只开一个 |

【强制】不把密钥写进命令行、镜像、Git、日志；由部署平台注入。

### 11.5 Liquibase 首次部署

```bash
java -jar hsmty-module-dm-start.jar \
  --spring.liquibase.enabled=true \
  --spring.datasource.url='jdbc:mysql://<host>:<port>/<db>?...'
```

检查：

1. `hs_dm_*` 表数量与设计一致。
2. 字典/初始化数据条数正确。
3. `DATABASECHANGELOG` 有 001–00N 记录。
4. 重复启动不重复执行。

之后按发布流程设回 `false`，由发布任务控制。

### 11.6 健康检查与冒烟

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://<host>:8080/hs-api/actuator/health   # 200
curl -s http://<host>:8080/hs-api/v3/api-docs/dm | head -c 200
curl -s -H "Cookie: SESSION=<会话>" http://<host>:8080/hs-api/dm/pool
```

页面冒烟：

1. 菜单可见。
2. 数据池列表/详情。
3. 方案新建/编辑/发布。
4. 任务启动/进度/停止/重跑。
5. 结果详情/下载/发布数据集。
6. 无权限账号 403。

### 11.7 回滚

1. 后端回退上一版镜像/jar。
2. 前端 nginx 指回上一版静态资源。
3. 数据库用发布前备份恢复；Liquibase 无 rollback 时不要手动删表。
4. UAP 菜单/权限回滚脚本（如提供）。
5. 只是权限问题时，补权限并重新登录，不回滚代码。

### 11.8 多副本

1. `worker-id` 每实例不同。
2. 定时任务/轮询只开一个。
3. 任务恢复用分布式锁。
4. 本地文件存储不能多副本共享时，改对象存储或共享卷。

### 11.9 上线检查单

见第 14.5 节。

---

## 12. 文档与协作

### 12.1 `docs/` 结构

```text
docs/
├── design/
│   ├── 01-需求说明书-DM.md
│   ├── 02-技术设计-DM.md
│   └── 03-功能追溯矩阵-DM.md
├── UAP权限注册清单-DM.md
├── algorithm/
│   ├── 算法对接说明.md
│   └── 变更说明.md
├── 前后端规范/           # 平台规范副本或链接
├── 前端规范/
└── BUILD-INFO.md
```

### 12.2 `contract/` 结构

见 5.5。每个域开工前重读 `VERSION`、`SYNC.md`、`api-contract.md`。

### 12.3 ADR

建议至少记录：

| ADR | 主题 |
| --- | --- |
| ADR-001 | 模块命名（dm / hs_dm_* / /hs-api/dm） |
| ADR-002 | 算法边界与文件传递模式（file/local/oss） |
| ADR-003 | 异步任务模型（业务表 + 通用任务表） |
| ADR-004 | 配比算法（最大余数法、去重顺序、种子） |
| ADR-005 | 数据集版本与发布策略 |

### 12.4 功能追溯矩阵

每条需求一行：编号、需求、实现（页面/接口/表）、状态、验证方式、备注。状态用：

| 状态 | 含义 |
| --- | --- |
| ✅ | 已实现并本地验证 |
| 🟡 | 已实现，待测试环境验证 |
| 🔶 | 已实现但有已知差异/约束 |
| ⛔ | 本期不做 |
| ❓ | 待确认 |

### 12.5 SYNC

记录：当前分支/提交、已完成、阻塞、本轮改动、下一步、待确认问题。三会话共同更新，父会话裁决。

### 12.6 交接

交接必须包含：

1. 代码分支与提交。
2. 构建/启动命令。
3. 环境变量与依赖。
4. 数据库变更与回滚。
5. 已知问题与限制。
6. 验收步骤与脚本。
7. 契约版本与算法基线。

---

## 13. 数据配比（DM）领域蓝图

> 本章是建议基线，不是最终需求。需求评审后按结论调整；调整时同步契约、表、接口、权限、页面。

### 13.1 业务假设

1. 用户先准备/导入数据池；数据池可由上传文件、ASC 数据集、LTP 素材或其他数据集组成。
2. 用户配置配比方案：选择 ≥2 个数据池，设置比例（合计 100%）、目标总量、质量阈值、去重策略。
3. 用户按方案发起配比任务；系统按快照异步执行，产出结果。
4. 结果可查看目标/实际比例、偏差、质量报告，并发布为数据集版本。
5. 任务可停止、重跑；结果可下载/预览；数据集版本不可变。

### 13.2 领域模型

```text
DataPool 1 ─── N DataPoolItem
   │
   └── N MixingPlanComponent ─── 1 MixingPlan 1 ─── N MixingPlanVersion
                                              │ 1
                                              └── N MixingTask 1 ─── 0..1 MixingResult
                                                                       │ 1
                                                                       └── 1 DatasetVersion ─── 1 Dataset

MixingTask 1 ─── N MixingTaskComponent（方案快照）
MixingTask 1 ─── N Task（通用异步任务，biz_type=mixing）
```

### 13.3 状态机

**数据池**

```text
draft → enabled → disabled
  └→ failed（导入/统计失败，可重试）
```

**配比方案**

```text
draft → enabled → disabled
  └→ draft（编辑草稿）
enabled 编辑 → 生成新版本（旧版本只读）
```

**配比任务**

```text
pending → running → completed
                 ├→ partial_failed（部分组分不足/部分失败，按策略）
                 ├→ failed
                 └→ stopping → stopped
failed/stopped/partial_failed → pending（重跑，新任务或重置）
```

**配比结果**

```text
generating → available → expired
          └→ failed
```

**数据集版本**

```text
draft → published → archived
```

### 13.4 表清单

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| `hs_dm_data_pool` | 数据池 | `pool_code`、`name`、`source_type`、`status`、`item_count`、`total_records`、`quality_score`、`version_no` |
| `hs_dm_data_pool_item` | 数据池条目 | `pool_id`、`source_type`、`source_id`、`file_name`、`file_key`、`record_count`、`content_hash`、`category`、`quality_score`、`meta_json` |
| `hs_dm_mixing_plan` | 配比方案 | `plan_code`、`name`、`scene_code`、`status`、`version_no`、`config_json` |
| `hs_dm_mixing_plan_component` | 方案组分 | `plan_id`、`pool_id`、`ratio`、`min_count`、`max_count`、`quality_threshold`、`dedup_policy`、`sort_no` |
| `hs_dm_mixing_plan_version` | 方案版本 | `plan_id`、`version_no`、`config_json`、`change_note`、`effective_time` |
| `hs_dm_mixing_task` | 配比任务 | `task_code`、`plan_id`、`plan_version`、`plan_snapshot`、`status`、`seed`、`target_total`、`actual_total`、`progress`、`algorithm_job_id`、`result_id` |
| `hs_dm_mixing_task_component` | 任务组分快照 | `task_id`、`pool_id`、`ratio`、`target_count`、`actual_count`、`source_snapshot` |
| `hs_dm_mixing_result` | 配比结果 | `result_code`、`task_id`、`dataset_version_id`、`target_total`、`actual_total`、`manifest_uri`、`content_hash`、`quality_report_json`、`status`、`expire_time` |
| `hs_dm_dataset` | 数据集 | `dataset_code`、`name`、`scene_code`、`status`、`current_version` |
| `hs_dm_dataset_version` | 数据集版本 | `dataset_id`、`version_no`、`result_id`、`record_count`、`manifest_uri`、`status`、`published_time` |
| `hs_dm_task` | 通用异步任务 | `task_no`、`biz_type`、`biz_id`、`status`、`progress`、`heartbeat_time` |
| `hs_dm_quality_report` | 质量报告（可选） | `result_id`、`report_json`、`report_uri`、`created_time` |

> 所有表含公共字段；表名以平台最终分配为准（本节按 `hs_dm_` 示例）。

### 13.5 API 清单

#### 数据池 `/pool`

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/pool` | `dm:pool:page` | 分页（name/sourceType/status） |
| GET | `/pool/options` | `dm:pool:option` | 下拉，仅 enabled |
| GET | `/pool/{id}` | `dm:pool:detail` | 详情 |
| GET | `/pool/{id}/items` | `dm:pool:detail` | 条目分页 |
| GET | `/pool/{id}/statistics` | `dm:pool:detail` | 条数/大小/质量分布 |
| POST | `/pool` | `dm:pool:create` | 新建 |
| PUT | `/pool` | `dm:pool:update` | 修改 |
| PUT | `/pool/status` | `dm:pool:status` | 启停 |
| DELETE | `/pool` | `dm:pool:remove` | 批量删除（被方案引用时拒绝） |
| POST | `/pool/{id}/import` | `dm:pool:import` | 导入文件/外部数据集（异步） |
| POST | `/pool/{id}/recount` | `dm:pool:update` | 重新统计 |

#### 配比方案 `/plan`

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/plan` | `dm:plan:page` | 分页 |
| GET | `/plan/options` | `dm:plan:option` | 下拉，仅 enabled |
| GET | `/plan/{id}` | `dm:plan:detail` | 详情（含组分） |
| GET | `/plan/{id}/versions` | `dm:plan:detail` | 版本历史 |
| POST | `/plan` | `dm:plan:create` | 新建 |
| PUT | `/plan` | `dm:plan:update` | 修改草稿 |
| PUT | `/plan/status` | `dm:plan:status` | 启停 |
| POST | `/plan/{id}/publish` | `dm:plan:publish` | 发布新版本 |
| POST | `/plan/{id}/copy` | `dm:plan:copy` | 复制 |
| DELETE | `/plan` | `dm:plan:remove` | 批量删除（被任务引用时拒绝） |

#### 配比任务 `/task`

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/task` | `dm:task:page` | 分页（planId/status/time） |
| GET | `/task/{id}` | `dm:task:detail` | 详情 |
| POST | `/task` | `dm:task:create` | 创建（可 `startNow`） |
| POST | `/task/{id}/start` | `dm:task:start` | 启动/重跑 |
| POST | `/task/{id}/stop` | `dm:task:stop` | 停止 |
| POST | `/task/{id}/retry` | `dm:task:retry` | 重跑失败 |
| GET | `/task/{id}/progress` | `dm:task:detail` | 进度 |
| DELETE | `/task` | `dm:task:remove` | 删除（进行中拒绝） |

#### 配比结果 `/result`

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/result` | `dm:result:page` | 分页 |
| GET | `/result/{id}` | `dm:result:detail` | 详情（比例/质量/清单） |
| GET | `/result/{id}/download` | `dm:result:download` | 下载结果文件 |
| GET | `/result/{id}/manifest` | `dm:result:detail` | 清单预览/分页 |
| POST | `/result/{id}/publish` | `dm:result:publish` | 发布数据集版本 |
| POST | `/result/{id}/expire` | `dm:result:expire` | 置过期 |

#### 数据集 `/dataset`

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/dataset` | `dm:dataset:page` | 分页 |
| GET | `/dataset/{id}` | `dm:dataset:detail` | 详情 |
| GET | `/dataset/{id}/versions` | `dm:dataset:detail` | 版本列表 |
| POST | `/dataset` | `dm:dataset:create` | 新建 |
| PUT | `/dataset` | `dm:dataset:update` | 修改 |
| DELETE | `/dataset` | `dm:dataset:remove` | 删除（有版本时拒绝） |
| POST | `/dataset/{id}/publish` | `dm:dataset:publish` | 发布版本 |
| POST | `/dataset/{id}/archive` | `dm:dataset:archive` | 归档 |

#### 看板 `/dashboard`（可选）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/dashboard/overview` | `dm:dashboard:page` | 数据池数/方案数/任务数/成功率 |

### 13.6 权限、菜单、字典、编号

**菜单**

| 菜单 | component | 页面权限 |
| --- | --- | --- |
| 数据配比（分组） | — | — |
| 数据池管理 | `/dm/pool/index` | `dm:pool:page` |
| 配比方案 | `/dm/plan/index` | `dm:plan:page` |
| 配比任务 | `/dm/task/index` | `dm:task:page` |
| 配比结果 | `/dm/result/index` | `dm:result:page` |
| 数据集管理 | `/dm/dataset/index` | `dm:dataset:page` |
| 任务详情 | `/dm/task/detail/index` | `dm:task:detail`（隐藏） |
| 结果详情 | `/dm/result/detail/index` | `dm:result:detail`（隐藏） |

**权限码**：见 9.2；总数约 40，按实际接口增减。

**字典**：见 4.5。

**编号**：见 4.6。

### 13.7 配比算法

#### 13.7.1 输入

- 方案快照：组分（池、比例、质量阈值、去重策略）、目标总量、随机种子、是否允许不足。
- 每个池的可用记录：过滤停用/删除/质量不达标后的记录。

#### 13.7.2 分配（最大余数法）

```text
target_i = floor(N * ratio_i / 100)
remainder_i = N * ratio_i / 100 - target_i
将剩余 R = N - Σtarget_i 按 remainder 从大到小依次 +1
```

示例：N=1000，比例 33.3/33.3/33.4：

```text
target = 333, 333, 334；remainder = 0.0, 0.0, 0.0；R=0
```

示例：N=100，比例 33.33/33.33/33.34：

```text
floor = 33, 33, 33；remainder = 0.33, 0.33, 0.34；R=1 → 第三个 +1 = 33,33,34
```

#### 13.7.3 抽样

1. 每个池内按稳定顺序（`id` 升序或 `content_hash` 升序）排序。
2. 过滤：`quality_score >= threshold`；停用/删除排除。
3. 去重：
   - `none`：不去重。
   - `exact_hash`：按 `content_hash` 保留第一条。
   - `semantic`：调用算法/向量去重，保留代表。
4. 抽样：`Random(seed)` 无放回；抽样前记录可用数。
5. 不足：
   - `allowShortage=false`（默认）：任务 `failed`，错误信息“池【x】需要 A，可用 B”。
   - `allowShortage=true`：取可用全部，任务 `partial_failed`，结果记录缺口。

#### 13.7.4 输出与校验

1. 按组分顺序合并；每条记录带 `sourcePoolId`、`sourceItemId`、`sourceRecordIndex`、`contentHash`。
2. 输出 JSONL；计算文件 SHA-256；写 manifest。
3. 校验：`actual_total == sum(actual_count)`；`actual_ratio = actual_count / actual_total * 100`；偏差 = 实际 - 目标。
4. 质量报告：各池可用数、过滤数、去重数、抽样数、重复率、质量分布、偏差。
5. 结果落库：目标/实际/偏差/哈希/manifest URI/算法 jobId/耗时。

#### 13.7.5 可复现

同一 `seed` + 同一方案版本 + 同一输入池快照 + 同一算法版本 → 同一结果哈希。任一变化必须记录在结果快照中。

### 13.8 页面结构

| 页面 | 结构 |
| --- | --- |
| 数据池管理 | Banner → 搜索卡（名称/来源/状态）→ 表格（名称/来源/条数/大小/质量/状态/时间/操作）→ 分页；新建/导入弹窗；详情抽屉（基础信息 + 条目列表 + 统计） |
| 配比方案 | Banner → 搜索卡 → 表格（名称/场景/组分数/目标总量/版本/状态/时间/操作）→ 分页；新建/编辑 86% 抽屉（基础信息 + 组分表格 + 比例合计 + 预览）；版本历史抽屉 |
| 配比任务 | Banner → 搜索卡（方案/状态/时间）→ 表格（任务号/方案/目标/实际/进度/状态/时间/操作）→ 分页；新建弹窗（选方案/总量/种子/立即启动）；详情抽屉（进度 + 组分 + 日志）；停止/重跑 |
| 配比结果 | Banner → 搜索卡 → 表格（结果号/任务/目标/实际/偏差/质量/状态/时间/操作）→ 分页；详情抽屉（比例对比表 + 质量报告 + 清单预览 + 下载 + 发布） |
| 数据集管理 | Banner → 搜索卡 → 表格（名称/场景/当前版本/条数/状态/时间/操作）→ 分页；详情抽屉（版本列表 + 发布/归档） |

### 13.9 异步与算法集成

- 配比任务默认走 `MixingGateway`；算法可用时 `AlgorithmMixingGateway`，否则 `LocalMixingGateway`（仅小数据量/开发）。
- 算法接口建议：`POST /mixing/jobs`、`GET /jobs/{id}`、`POST /jobs/{id}/cancel`、`GET /artifacts/{jobId}/{name}`、`GET /health`。
- 文件模式 `file`：先 `POST /files` 上传池文件，拿 `fileId`；任务请求只传 `fileId`。
- 结果文件由算法写对象存储/共享卷，DM 只存 URI；下载走 DM 后端代理或预签名。
- 任务状态映射见 7.6；失败分类见 6.8。

### 13.10 验收用例

见 10.6；补充：

1. 比例 33.33/33.33/33.34，N=100 → 33/33/34。
2. 比例 60/40，N=101 → 61/40 或 60/41（按最大余数，记录规则）。
3. 某池可用不足 → 默认 failed，提示需要/可用。
4. 去重后不足 → 同上。
5. 同 seed 重跑 → 结果哈希一致。
6. 不同 seed → 结果不同但比例在容差内。
7. 结果发布数据集 → 版本不可变；再次发布生成新版本。
8. 结果过期 → 下载拒绝，提示已过期。

### 13.11 分期计划

| 阶段 | 内容 | 产出 |
| --- | --- | --- |
| P0 | 命名/号段/契约/需求评审 | 命名确认、API 契约 v0.1、权限清单 |
| P1 | 工程改名、启动、Liquibase 001 | 可启动空服务 + 表 |
| P2 | 数据池 CRUD/导入/统计 | 数据池页可联调 |
| P3 | 方案 CRUD/组分/版本 | 方案页可联调 |
| P4 | 任务框架/状态机/本地配比 | 任务页可联调（本地结果） |
| P5 | 算法对接/结果/质量报告 | 真实结果 |
| P6 | 数据集版本/发布/下载 | 数据集页 |
| P7 | 权限/测试/部署/验收 | 可提测版本 |

---

## 14. 检查清单

### 14.1 新模块启动

- [ ] 模块名、domain、包名、API 前缀、表前缀、权限码、字典前缀、编号前缀已确认。
- [ ] 菜单号段、字典号段已申请。
- [ ] 数据库/Redis/算法/存储地址已确认。
- [ ] 需求说明书、技术设计、契约初稿完成。
- [ ] 模板 `xxx` 全部替换，无残留。
- [ ] 启动成功，Swagger 分组正确。
- [ ] Liquibase 001 建表成功且幂等。

### 14.2 后端 PR

- [ ] Controller 有 `@Tag/@Operation/@PreAuthorize`，返回 `ApiResult`。
- [ ] Service 有校验/事务/断言，远程调用在事务外。
- [ ] PO 继承 BaseEntity，逻辑删除，审计字段由监听器填充。
- [ ] DTO/VO 字段有 `@Schema`，查询 DTO 继承 PageQuery。
- [ ] 表名/字段/Liquibase/Mapper XML 一致。
- [ ] 新 changeSet 有 preConditions，未改历史 changeSet。
- [ ] 权限码三处一致。
- [ ] 无敏感信息、无 `System.out`、无吞异常。
- [ ] 单测/集成测试通过（显式执行）。
- [ ] 契约/OpenAPI 已更新。

### 14.3 前端 PR

- [ ] `register.ts` key 与菜单 component、文件路径一致。
- [ ] API 走 `createModuleHttp('dm','/hs-api/dm')`。
- [ ] 类型与契约一致，Long 用 string。
- [ ] 列表用 ProTable；详情用抽屉；表单校验完整。
- [ ] 按钮权限 `can()` 控制，后端仍有校验。
- [ ] 轮询终态停止、卸载清理。
- [ ] 样式作用域，未改公共层。
- [ ] `pnpm type-check`、`pnpm build` 通过。

### 14.4 提测

- [ ] 构建产物版本/哈希记录。
- [ ] 数据库变更已在测试库执行。
- [ ] UAP 菜单/权限已录入并授权。
- [ ] 算法/存储/Redis 可用。
- [ ] 主流程 + 边界脚本通过。
- [ ] 已知问题/限制已书面说明。

### 14.5 上线

- [ ] 生产数据库备份。
- [ ] 环境变量/密钥已注入。
- [ ] Liquibase 首次执行并核对。
- [ ] 后端健康、前端资源、菜单权限正常。
- [ ] 冒烟通过。
- [ ] 回滚方案确认。
- [ ] 监控/日志/告警可用。

### 14.6 权限

- [ ] 权限码清单与 `@PreAuthorize` 逐条一致。
- [ ] 菜单 component 与前端一致。
- [ ] 角色菜单授权 `role/disAuth` 完成。
- [ ] 角色资源授权完成。
- [ ] `permissions/verify` 含 `dm:*`。
- [ ] 无权限账号 403/菜单不可见。

---

## 15. 经验与反模式

### 15.1 LTP 真实踩坑

| 问题 | 现象 | 根因 | 规范动作 |
| --- | --- | --- | --- |
| 停止被完成覆盖 | 日志 stopped 后 completed | 停止与落库无互斥，未重读状态 | 按 ID 锁 + 落库前重读 + CAS |
| 共享存储路径不一致 | `文件不存在` | 后端与算法挂载点不同 | 优先 `file` 上传；共享卷必须同路径同权限 |
| 内部令牌连不上 | 401 | 令牌值/环境变量名不一致 | 与算法方对齐；关闭校验则留空；不猜 |
| 菜单白屏 | 路由能进但页面空 | component 与 register key 不一致 | 三处一致检查 |
| Long 精度丢失 | ID 末位变 0 | JS Number 精度 | 后端序列化 string，前端 string |
| 不适用指标显示 0 | 结果矩阵误导 | `applicable=false` 未置 null | 强制 null，前端 `—` |
| 唯一索引 + 逻辑删除冲突 | 重跑插入失败 | 唯一索引阻挡 | 关联/结果表用普通索引 |
| 测试被跳过 | BUILD SUCCESS 但没跑 | `skipTests=true` | 显式 `-DskipTests=false` 并核对执行数 |
| Jasypt 默认密码 | 生产解密风险 | 未注入 `JASYPT_ENCRYPTOR_PASSWORD` | 生产必须换 |
| 后端无 test 分支 | Jenkins 构建不到 | 分支策略未确认 | 上线前确认 Job Branch Specifier |

### 15.2 ASC 真实踩坑

| 问题 | 现象 | 根因 | 规范动作 |
| --- | --- | --- | --- |
| Noop 网关 | 任务停 RUNNING | 真实算法未接入，空实现只记日志 | Noop 明确失败；任务落 failed |
| 种子原文为空 | `seed_content` null | 种子在算法容器内，业务读不到 | 算法提供查询接口或配置目录 |
| 多副本主键冲突 | 雪花重复 | `worker-id` 相同 | 每实例不同 |
| 部分失败 | 任务 completed 但样本不足 | 未区分 partial_failed | 单独状态 + 缺口报告 |
| 供给包无下载 | 只有记录 | 接口未实现 | 契约标 partial，不假装可用 |
| 策略数量变化 | 16 → 100 | 算法动态目录 | 启动同步 `/v1/methods`，不写死 |

### 15.3 通用反模式

1. **先写代码后补契约**：字段/状态各说各话，联调返工。
2. **状态只有 running/completed**：无法表达停止、部分失败、重试。
3. **异步任务不落库**：重启即丢，无法恢复/审计。
4. **事务包远程调用**：连接占用、回滚不了远程副作用。
5. **Controller 写业务**：无法复用、无法测试。
6. **PO 直接返回前端**：暴露审计字段/敏感字段，字段一变就破。
7. **前端硬编码权限/枚举**：菜单一改就错。
8. **详情用弹窗**：字段多、滚动、丢上下文。
9. **大文件 readAllBytes**：OOM。
10. **日志打印请求体/令牌**：安全事故。
11. **共享目录当网络盘**：路径/权限/多副本问题。
12. **算法产物复制进业务库**：库膨胀、版本混乱。
13. **没有 seed/快照**：结果不可复现。
14. **没有幂等**：重复点击产生重复任务。
15. **测试只跑 happy path**：边界/并发/恢复上线才爆。

---

## 附录 A：代码模板

### A.1 Controller

```java
@Tag(name = "数据池")
@RestController
@RequestMapping("pool")
@RequiredArgsConstructor
@Validated
public class DataPoolController {

    private final DataPoolService dataPoolService;

    @Operation(summary = "分页查询数据池")
    @PreAuthorize("hasAnyAuthority('dm:pool:page')")
    @GetMapping
    public ApiResult<PageResult<DataPoolVO>> page(DataPoolListDTO dto) {
        return ApiPageResult.success(dataPoolService.page(dto));
    }

    @Operation(summary = "查询数据池详情")
    @PreAuthorize("hasAnyAuthority('dm:pool:detail')")
    @GetMapping("/{id}")
    public ApiResult<DataPoolVO> detail(@PathVariable Long id) {
        return ApiResult.success(dataPoolService.detail(id));
    }

    @Operation(summary = "新增数据池")
    @PreAuthorize("hasAnyAuthority('dm:pool:create')")
    @PostMapping
    public ApiResult<Void> create(@Valid @RequestBody DataPoolCreateDTO dto) {
        dataPoolService.create(dto);
        return ApiResult.success();
    }
}
```

### A.2 Service

```java
@Service
@RequiredArgsConstructor
public class DataPoolServiceImpl extends ServiceImpl<DataPoolMapper, DataPoolEntity>
        implements DataPoolService {

    private final DmBizCodeGenerator codeGenerator;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void create(DataPoolCreateDTO dto) {
        CommonResponseEnum.INVALID.message("数据池名称不能为空")
                .assertTrue(!Utils.isNotNull(dto.getName()));
        DataPoolEntity entity = BeanCopyUtils.copy(dto, DataPoolEntity.class);
        entity.setPoolCode(codeGenerator.nextPoolCode());
        entity.setStatus(PoolStatus.DRAFT.name());
        save(entity);
    }

    @Override
    public PageResult<DataPoolVO> page(DataPoolListDTO dto) {
        Page<DataPoolVO> page = pageAs(PageUtils.getPage(dto), buildQueryWrapper(dto), DataPoolVO.class);
        return PageUtils.getPageResult(page);
    }

    private QueryWrapper buildQueryWrapper(DataPoolListDTO dto) {
        QueryWrapper wrapper = QueryWrapper.create();
        if (Utils.isNotNull(dto.getName())) {
            wrapper.like(DataPoolEntity::getName, dto.getName());
        }
        if (Utils.isNotNull(dto.getStatus())) {
            wrapper.eq(DataPoolEntity::getStatus, dto.getStatus());
        }
        return wrapper.orderBy(DataPoolEntity::getCreateTime, false);
    }
}
```

### A.3 Liquibase

```xml
<changeSet id="dm-create-pool-20261116" author="your-name" context="mysql,postgresql">
  <preConditions onFail="MARK_RAN">
    <not><tableExists tableName="hs_dm_data_pool"/></not>
  </preConditions>
  <createTable tableName="hs_dm_data_pool" remarks="数据池">
    <column name="id" type="BIGINT" remarks="主键ID">
      <constraints primaryKey="true" nullable="false"/>
    </column>
    <column name="pool_code" type="VARCHAR(16)" remarks="数据池业务编号">
      <constraints nullable="false"/>
    </column>
    <column name="name" type="VARCHAR(100)" remarks="数据池名称">
      <constraints nullable="false"/>
    </column>
    <column name="status" type="VARCHAR(20)" remarks="状态" defaultValue="draft">
      <constraints nullable="false"/>
    </column>
    <column name="create_id" type="BIGINT" remarks="创建人ID"/>
    <column name="create_time" type="DATETIME" remarks="创建时间"/>
    <column name="update_id" type="BIGINT" remarks="更新人ID"/>
    <column name="update_time" type="DATETIME" remarks="更新时间"/>
    <column name="del_flag" type="CHAR(1)" remarks="删除标记" defaultValue="F">
      <constraints nullable="false"/>
    </column>
  </createTable>
  <createIndex tableName="hs_dm_data_pool" indexName="idx_dm_pool_code">
    <column name="pool_code"/>
  </createIndex>
</changeSet>
```

### A.4 前端模块注册

见 8.1。

### A.5 前端 API

见 8.3。

### A.6 异步执行器

见 6.4。

### A.7 算法网关

```java
public interface MixingGateway {
    SubmitResult submit(MixingRequest request);
    JobStatus query(String jobId);
    void cancel(String jobId);

    record SubmitResult(String jobId, String status) {}
}
```

---

## 附录 B：术语表

| 术语 | 说明 |
| --- | --- |
| 数据池 | 可参与配比的数据集合，含来源、规模、质量信息 |
| 配比方案 | 数据池 + 比例 + 质量/去重规则 + 目标总量的可复用配置 |
| 配比任务 | 按方案快照执行的一次异步作业 |
| 配比结果 | 任务产出的数据集文件/清单与比例/质量报告 |
| 数据集版本 | 不可变的结果快照，可发布/归档 |
| 组分 | 方案中的一个数据池及其比例 |
| 目标比例 / 实际比例 | 方案设定 vs 实际产出占比 |
| 偏差 | 实际比例 - 目标比例 |
| 快照 | 启动时冻结的方案/输入/算法版本，保证可复现 |
| 种子 | 随机抽样种子，保证结果可复现 |
| 幂等键 | 防止重复提交的请求标识 |
| UAP | 平台统一权限管理 |
| SSO Cookie | 平台登录态，不是 Bearer Token |

---

## 附录 C：参考文档

| 文档 | 路径 |
| --- | --- |
| 后端模板规范 | `C:\Users\Aurora\Desktop\asc\docs\前后端规范\CLAUDE.md` |
| 前端开发规范 | `C:\Users\Aurora\Desktop\ltp\hsmty-web\docs\前端开发规范.md` |
| UI 设计规范 | `C:\Users\Aurora\Desktop\asc\docs\前端规范\【设计规范】平台UI样式设计规范V4-1025.md` |
| ID 生成规范 | `C:\Users\Aurora\Desktop\asc\docs\前后端规范\【设计规范】平台相关ID生成规范-1026.md` |
| LTP 需求 | `C:\Users\Aurora\Desktop\ltp\docs\design\01-需求说明书-LTP.md` |
| LTP 技术设计 | `C:\Users\Aurora\Desktop\ltp\docs\design\02-技术设计-LTP.md` |
| LTP 契约 | `C:\Users\Aurora\Desktop\ltp\contract\` |
| ASC 契约 | `C:\Users\Aurora\Desktop\asc\contract\` |
| ASC 上线检查单 | `C:\Users\Aurora\Desktop\asc\docs\测试环境上线检查单.md` |
| 算法对接（LTP） | `C:\Users\Aurora\Desktop\ltp\docs\ltp算法服务对接文档.md` |
| 算法对接（ASC） | `C:\Users\Aurora\Desktop\asc\docs\asc算法服务对接文档.md` |

---

> 本规范由 LTP 与 ASC 的落地经验整理而成。DM 开工后，每发现一条新的平台约束或踩坑，追加到第 15 章，并同步到团队规范，避免下一个模块重复。


---

# 附录 D：2026-11-18 LTP 异步实现统一改造（甲方要求）

## D.1 背景

LTP（value-lab）与 asc 等业务模块采用**合并部署**。甲方评审时提出：各模块异步实现不统一，要求统一使用 Spring 的 `@Async`；对于类内部调用导致 `@Async` 不生效的问题，按甲方要求用 `SpringUtil.getBean()` 取代理对象再调用。

本轮只改 LTP 后端，不修改 asc 代码。

## D.2 甲方原话

> 各模块的异步实现不统一，要求统一使用 Spring 的 `@Async`；对于类内部调用导致 `@Async` 不生效的问题，按甲方要求用 `SpringUtil.getBean()` 取代理对象再调用。

## D.3 改造前（LTP）

- `ValueLabEvalTaskExecutor` 使用 `Executors.newVirtualThreadPerTaskExecutor()` + `Semaphore(maxConcurrent)`；
- 超出并发的任务在虚拟线程中挂起，没有显式队列容量、没有拒绝策略；
- 异常在 `submit` 内部被 `catch (Throwable)` 吞掉并只打日志；
- 没有 `AsyncUncaughtExceptionHandler`，没有 MDC/TraceId 传递；
- `ValueLabTaskProperties.heartbeatSeconds` 配置存在但代码未使用；
- 任务可靠性依赖 `ValueLabStaleTaskRecoverJob` 的心跳/残留恢复。

## D.4 改造后（LTP）

### D.4.1 统一线程池

新增 `com.hsmty.configuration.ValueLabAsyncConfiguration`：

- `@EnableAsync`；
- Bean 名 `applicationTaskExecutor`，类型 `ThreadPoolTaskExecutor`；
- 显式配置 `corePoolSize / maxPoolSize / queueCapacity / threadNamePrefix / keepAliveSeconds`；
- 拒绝策略 `ThreadPoolExecutor.AbortPolicy`，队列满抛 `TaskRejectedException`，不静默丢弃；
- `TaskDecorator` 传递 MDC（traceId），任务结束恢复原上下文；
- `AsyncConfigurer` 注册 `AsyncUncaughtExceptionHandler`，记录方法名、taskNo 与异常栈。

配置项：

```yaml
value-lab:
  task:
    core-pool-size: 4
    max-pool-size: 4
    queue-capacity: 100
    thread-name-prefix: value-lab-task-
    keep-alive-seconds: 60
    stale-minutes: 2
    recover-interval-ms: 300000
```

### D.4.2 `@Async` 入口

`ValueLabEvalTaskExecutor` 改为 `ValueLabAsyncTaskRunner`：

```java
@Async("applicationTaskExecutor")
public void submit(String taskNo, Runnable task) {
    // 只负责执行；异常交给 AsyncUncaughtExceptionHandler
    task.run();
}
```

业务 Service 通过构造器注入 `ValueLabAsyncTaskRunner` 后调用，属于**跨 Bean 调用**，`@Async` 代理生效，不存在自调用问题。

### D.4.3 自调用处理

本轮未使用 `SpringUtil.getBean()`，原因：

- `ValueLabAsyncTaskRunner` 是独立 Bean，业务 Service 注入后调用，天然经过代理；
- 不引入“同类自调用”问题，代码更清晰、可测试；
- 甲方要求的目标是 `@Async` 生效，本方案已满足。

如果后续确实出现同类自调用，按甲方约定使用 `SpringUtil.getBean(ValueLabAsyncTaskRunner.class)` 取代理对象再调用；必须**在方法入口取一次**，禁止在循环内反复 `getBean`，并在注释中标注“甲方约定，勿改回自调用”。当前代码不需要该写法。

### D.4.4 队列满处理

- `ValueLabMaterialStatServiceImpl.submit`：捕获 `TaskRejectedException`，将素材统计置失败，提示“任务队列已满，请稍后重试”；
- `ValueLabExperimentEvalServiceImpl.submit`：捕获后调用 `fail(...)`，任务与实验置失败；
- `ValueLabConclusionServiceImpl.submit`：捕获后标记任务/结论失败；
- 三个 `recover` 方法：捕获后只记录 warn，保留 running 状态，交给下一轮残留扫描继续恢复，不在恢复入口误判失败。

## D.5 可靠性机制（保留，未删除）

- 心跳：由 `ValueLabEvalTaskService.updateProgress` 在每次轮询/进度更新时写入 `heartbeat_time`；
- 启动恢复：`ValueLabStaleTaskRecoverJob` 启动时扫描所有 `RUNNING` 任务；
- 定时恢复：每 `recover-interval-ms` 扫描，心跳超过 `stale-minutes` 的视为残留；
- 有 `algorithm_job_id` 的继续轮询；没有的置 `failed(TASK_STALE)`；
- 任务状态仍以数据库 `hs_value_lab_eval_task` 为准，重启后可恢复或置失败。

`heartbeat-seconds` 已删除：心跳不是独立定时器写入，而是由进度更新写入；保留一个未使用的配置会误导部署。当前算法轮询 2s/5s、本地统计有进度回调，均小于 `stale-minutes=2` 的阈值。

## D.6 虚拟线程说明

本轮改为平台线程池，未继续使用虚拟线程。理由：

- 甲方要求统一 `@Async`，`ThreadPoolTaskExecutor` 的**有界队列 + 拒绝策略**语义明确、可观测；
- 虚拟线程没有“队列容量/拒绝策略”的直接对应物，若用 `SimpleAsyncTaskExecutor` + 虚拟线程工厂，需要另行设计排队与拒绝，容易偏离统一方案；
- 当前并发上限 4、任务为 IO/算法轮询型，平台线程足够。

如后续确需虚拟线程，建议单独 ADR 评估，不要直接在本配置上替换线程工厂。

## D.7 验证结果

- 编译：`mvn -s settings.xml -pl hsmty-module-value-lab-core,hsmty-module-value-lab-start -am clean package -DskipTests` → BUILD SUCCESS；
- core 单测：71 通过，0 失败；
- start 单测：5 通过，1 跳过（`RealAlgorithmE2ETest` 需真实算法环境）；
- 新增 `ValueLabAsyncConfigurationTest`：
  - 并发上限生效（core=2/max=2/queue=1）；
  - 队列满抛 `TaskRejectedException`；
  - `AsyncUncaughtExceptionHandler` 输出错误日志；
- 启动验证：`ValueLabAsyncConfiguration` 打印 `core=2, max=4, queue=100, prefix=value-lab-task-`，应用 `Started RunApplication`；
- 运行时验证：上传 `.jsonl` 素材后，异步统计状态从 `running` 到 `success`，记录数 2；
- 残留恢复：`ValueLabStaleTaskRecoverJobTest` 通过，启动恢复与定时恢复行为未变。

## D.8 已知限制与后续待办

1. `void @Async` 抛出的未捕获异常由处理器记录，但任务表可能保持 `RUNNING`，最终由残留恢复置失败；若需“异常立即落库”，后续可在 Runner 内捕获并回写任务状态。
2. 队列容量 100 是初始值；高并发场景按实际压测调整 `queue-capacity`，不要改回无界队列。
3. 未使用 `SpringUtil.getBean()`；如甲方后续强制要求统一写法，按 D.4.3 的约定改造，避免循环内取 Bean。
4. `heartbeat-seconds` 已删除；如后续新增“长时间无进度”的本地计算步骤，需要补定时心跳或更细的进度回调。
5. 虚拟线程未启用；如后续启用，单独评估排队/拒绝语义。

## D.9 asc 侧做法（供跨模块对齐）

asc 没有自定义线程池，也没有使用 `@Async`。其异步模型是：

- HTTP 提交算法作业（202 + jobId）；
- `@Scheduled` 轮询作业状态；
- 数据库任务状态为权威；
- 本轮只补 `spring.task.scheduling.pool.size=4`，不需要改造成 `@Async`。

因此两个模块的异步形态不同但边界一致：

| 模块 | 异步方式 | 适用场景 |
| --- | --- | --- |
| LTP | `@Async` + 有界线程池 | 进程内素材统计、评测轮询、结论生成 |
| asc | HTTP 202 + `@Scheduled` 轮询 | 外部算法作业，作业生命周期由算法服务管理 |

共同点：任务状态落库、心跳/超时/恢复机制保留、前端只轮询业务状态，不依赖线程池内部状态。
