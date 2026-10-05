# AI 视频工坊任务建单实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有 `tiktok_studio` 模块中完成视频管线的第一步：运营输入产品货号，查看货号展开出的 ASIN/颜色/店铺，勾选确认后创建一个批次及每个 ASIN 对应的待准入任务。左侧模块标题显示为“AI视频工坊”。

**Architecture:** 建单在管线外同步完成。预览只查询货号映射并返回警告，不创建编排数据；确认后在单一数据库事务中校验并持久化批次和任务。仅新增 `batch`、`task` 两张表。当前管线固定为 `video_gen_15s`，标识保存在批次与任务中；本期不做管线定义管理、运营配额管理或日配额校验。任务初始为 `admitted_pending`，此阶段不创建 node，也不启动任何 worker。实现遵循 `tiktok_studio` 模块边界，数据与迁移归属 `mod_tiktok_studio`。

**Inputs:** `docs/history/架构设计-V4.0.0.md` §2.1、§6.1–6.4、§7.7、§15；`docs/history/架构设计-V5.0.0.md` §1.2–1.4、§3.2、§6.3；`docs/架构规范.md`。

## Decisions And Preconditions

- `ModuleSpec.title` 是左侧模块侧栏标题和应用切换器名称；保留技术模块名 `tiktok_studio`，把展示名改成“AI视频工坊”，不新建第二个技术模块。模块内新增“任务建单”导航项。
- 当前 `product_lookup` Tool 明确读取 mock JSON，本计划复用其输入输出契约做预览，但这不构成生产数据源。接真实 OMS/OS/飞书 API 之前，须确认来源、字段映射、超时和失败语义；不得把 mock 命中当作可上线的商品映射。
- 展开返回字段沿用 V4：`sku`、`asin`、`color`、`shop`、`warnings`。现有 Tool 的 `store` 映射为 API 的 `shop`。不完整映射（ASIN 为空）显示并警告，不能进入已勾选创建项。
- V4 的 `uk_task_batch_bizkey(batch_id, biz_key)` 只能阻止同一批次内的重复 ASIN，不能防止创建请求重试时生成第二个新批次。因此新增调用方生成的 `request_id` 和服务端计算的规范化 payload hash，由服务端按创建者唯一约束实现请求幂等；同 key 同 hash 重放返回原批次，同 key 不同 hash 返回 `409`。
- 当前 V5 对数据权限描述了平台 `auth.data_scope()`，但仓库是否已有可调用实现需在任务开始时核实。建单预览的“已有在途任务”警告至少只查询当前运营可见范围；不得为提示重复而泄露其他运营批次信息。
- 当前管线 key 固定为 `video_gen_15s`，写入 `batch` 与 `task`；本期不需要 `pipeline_definition` 表或可配置的管线版本解析。
- 本期不做日配额校验或持久化运营配额；V5 的 `operator_quota` 在准入调度实现时再引入，并确保与调度器同时交付。

## Scope

**本次包含：**

- 左侧模块显示名“AI视频工坊”及“任务建单”导航入口。
- 货号输入、展开预览、映射警告、逐行勾选、批次元信息填写、确认创建、结果反馈。
- 建单预览与批次创建 API、对应权限、`batch` / `task` 模型和迁移。
- 请求幂等与单批次 ASIN 去重。
- 后端 API/服务测试和前端 lint/typecheck。

**明确不做：**

- 准入放量、node 创建、管线 worker、任何视频生成或 seedance 通道。
- 批次/任务列表与详情、暂停/恢复/取消、追加任务、审核台、发布台。
- 管线编辑器、审核覆盖设置、优先级配置 UI、跨模块数据权限平台能力。
- 本地 mock 数据的生产化改造；真实商品源未确认时只允许开发/测试验证。
- 商品主数据导入、Amazon 抓取、三视图、模板匹配、提示词或视频生成。

## Data And API Contract

### Preview

`POST /api/tiktok_studio/orders/preview`

```json
{
  "skus": ["SKU12345", "SKU67890"]
}
```

返回输入顺序稳定的展开项：

```json
{
  "items": [
    { "sku": "SKU12345", "asin": "B0AAA", "color": "black", "shop": "US-01", "warnings": [] },
    { "sku": "SKU67890", "asin": null, "color": "red", "shop": null, "warnings": ["未找到 ASIN"] }
  ]
}
```

- 按现有 `importing.normalize_skus()` 规则做大写、拆分和稳定去重；API 直接调用时也执行规范化。
- `warnings` 至少覆盖无 ASIN、同一展开请求内重复 ASIN、当前用户已有未完成任务。已有任务只是提醒，不自动阻止跨批次复做。
- 单个货号查找失败时，在对应输入行返回可展示的错误；不把未查到的数据静默变成空成功结果。
- 预览不落库、不预占配额；创建 API 必须重新验证输入项/映射合法性，不能信任浏览器提交的预览对象。

### Create Batch

`POST /api/tiktok_studio/batches`

```json
{
  "request_id": "client-generated-uuid",
  "name": "0928 新品",
  "pipeline_key": "video_gen_15s",
  "items": [
    { "sku": "SKU12345", "asin": "B0AAA", "color": "black", "shop": "US-01" }
  ],
  "note": null
}
```

在一个事务内：

1. 对 `(created_by, request_id)` 做幂等查询/唯一约束；持久化规范化请求的 `request_hash`。同 key 同 hash 返回既有批次，同 key 不同 hash 返回 `409`。
2. 校验固定 `pipeline_key = video_gen_15s`，不解析管线定义表。
3. 去重并验证所选 ASIN 属于有效预览结果；同批次 ASIN 不重复。
4. 插入 `batch` 和每个 ASIN 一条 `task`，任务 `biz_key = asin`、`context = {sku, asin, color, shop}`、`status = admitted_pending`。
5. 不创建 node；返回批次 ID 和任务数。

批次上限沿用 V4 的 2000 个任务。`name` 必填；当前只有 `video_gen_15s`，`priority` 使用默认值；本阶段不暴露 `review_overrides` 编辑，但批次表保留空覆盖快照字段。

## Files

| 文件 | 动作 | 职责 |
|---|---|---|
| `server/modules/tiktok_studio/models.py` | 改 | 仅增加 `Batch`、`Task` 两张表；均位于 `mod_tiktok_studio`，用户外键只引用 `platform.user.id` |
| `server/modules/tiktok_studio/schemas.py` | 改 | 建单预览、确认创建、返回 DTO 和状态字段 |
| `server/modules/tiktok_studio/service.py` | 改 | 展开查询、警告判定、事务建单与幂等处理 |
| `server/modules/tiktok_studio/api.py` | 改 | 新增 preview/create endpoints 和权限校验；路由保持薄层 |
| `server/modules/tiktok_studio/module.py` | 改 | 模块 title 改为“AI视频工坊”，声明 `order:preview` / `batch:create` 权限和“任务建单”菜单 |
| `server/modules/tiktok_studio/migrations/versions/` | 新 | `0008` 创建两张表，`0009` 增加生命周期字段；不改写已应用迁移 |
| `server/tests/modules/tiktok_studio/test_task_creation_api.py` | 新 | 预览、逐项失败隔离、警告、权限、映射重验、建单与幂等测试 |
| `web/src/modules/tiktok_studio/index.ts` | 改 | 增加 `task-create` 路由及权限 meta |
| `web/src/modules/tiktok_studio/api.ts` | 改 | 类型化 preview/create 客户端 |
| `web/src/modules/tiktok_studio/views/TaskCreateView.vue` | 新 | 建单两阶段工作流 UI |

## Implementation Tasks

### Task 1: 数据模型和迁移

**Files:** `models.py`、`migrations/versions/`、模型测试。

- [x] 先检查 `alembic -n tiktok_studio history` 与分支当前 head，确认 revision ID 未占用。
- [x] 仅添加 `batch`、`task` 模型及 V4 所需唯一约束、索引；使用 `BIGINT` 用户 ID 并引用 `AppUser.id`。
- [x] `batch` 增加 `request_id` 与 `request_hash`，添加 `(created_by, request_id)` 唯一约束以支撑幂等重放和 payload 冲突校验。
- [x] 在 `batch` 和 `task` 中记录固定 `pipeline_key = video_gen_15s`，不新增定义表或种子数据。
- [x] 按本模块分支生成 `0008`、`0009` 迁移并审阅 schema、索引、FK、默认值和 downgrade；`0009` 承载已执行 `0008` 后补齐的生命周期列。
- [x] 在全新隔离测试数据库升级 platform 与 tiktok_studio 分支，并通过 `alembic -n tiktok_studio check`。

### Task 2: 建单服务与 API

**Files:** `schemas.py`、`service.py`、`api.py`、`module.py`、API tests。

- [x] 实现货号规范化与预览展开，注入/复用 `product_lookup`；将 Tool 的 `store` 映射到 `shop`。
- [x] 实现 warnings，查询当前运营的在途任务；覆盖 ASIN 为空、展开内重复、既有任务和单货号查找失败。
- [x] 实现批次创建事务、固定管线 key 校验、ASIN 映射重验和 request_id/request_hash 幂等；本期不做日配额校验。
- [x] 声明 `tiktok_studio:order:preview` 与 `tiktok_studio:batch:create` 权限并在接口校验。
- [x] 测试建单/任务写入、同 request_id 重放、不同 payload 冲突、映射伪造和重复 ASIN 拒绝、无权限拒绝。
- [x] 跑建单端到端测试、`pytest tests/modules/tiktok_studio` 和平台架构测试。

### Task 3: 前端建单流程与左侧入口

**Files:** `index.ts`、`api.ts`、`TaskCreateView.vue`、必要的模块局部样式。

- [x] 将模块展示标题设为“AI视频工坊”；新增“任务建单”一级导航，路由 `tiktok_studio/task-create`，权限码与后端对应。
- [x] 第一步：多行输入货号、预览按钮、结果表格；展示 ASIN/颜色/店铺/warnings，默认只勾选可创建项，允许运营逐行选择。
- [x] 第二步：填写批次名称和备注，显示所选任务数；请求进行中禁用重复提交并维持同一 `request_id` 以便网络重试。
- [x] 成功后显示批次编号和创建数量；失败保留输入与勾选，展示可恢复错误。
- [x] 不在本页面加入任务进度、审核、暂停或视频生成操作。
- [x] 运行 `cd web && npm run lint && npm run typecheck` 和生产构建。

### Task 4: 集成验收

- [x] 运行 `pytest tests/modules/tiktok_studio/test_task_creation_api.py tests/platforms/test_architecture.py`。
- [x] 在全新隔离数据库升级 platform 与 tiktok_studio 分支，并通过 tiktok_studio `alembic check`。
- [x] 运行仓库要求的全量 `pytest` 与前端 lint/typecheck/build。
- [x] 浏览器验收建单页预览、初始选择、无 ASIN 禁选、在途提示、创建成功；390px 视口确认无页面横向溢出，表格局部滚动。
- [ ] 上线前接入并确认真实产品数据源；当前 `product_lookup` 仍读 mock，不视作生产验收通过。

## Acceptance Criteria

- 左侧模块名称显示“AI视频工坊”，有“任务建单”入口，前后端权限码一致。
- 货号预览不产生持久化副作用，字段准确展示并含可解释警告。
- 每次成功确认只产生一个批次，每个有效 ASIN 一条 `admitted_pending` task，`task.context` 仅包含确认过的 sku/asin/color/shop。
- 创建事务只写 `batch` 与 `task`，保存固定管线 key，并满足 request_id 幂等；不产生孤儿批次或重复任务。本期不做日配额及 operator quota。
- 本阶段无 node、worker、视频生成、审核与发布行为。
- 模块迁移 upgrade/check、服务端相关测试、全量后端测试、前端 lint/typecheck 通过。