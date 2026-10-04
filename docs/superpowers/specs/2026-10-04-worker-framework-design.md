# Worker 框架设计

日期：2026-10-04
状态：待评审

## 背景与目标

当前框架只能运行 API 进程：`main.py` 只启动 uvicorn，`ModuleSpec` 没有声明后台逻辑的位置，数据库会话只能通过
FastAPI 依赖 `get_session` 获得。业务模块普遍会有后台需求（数据同步、定时清理、报表生成、AI 生成任务、对账），
目前没有宿主进程可以运行它们。`on_startup` 不能代替：它在 API 进程的 lifespan 中执行，API 一旦多开 uvicorn
worker，后台协程会被复制多份，也违背「API 不执行后台逻辑」的分层。

本次工作为框架补上通用的 worker 骨架：平台负责托管进程，后台逻辑由模块自己实现，保持模块独立，
任何模块连同自己的 worker 都能低成本拆出去。

运行平台：本地开发与生产部署均为 Linux。

## 范围

做：

- `ModuleSpec.loops` 声明后台循环，`BackgroundLoop` / `LoopContext` 契约
- `python main.py worker <模块>[,<模块>] [--loops a,b]` 入口
- 循环托管：异常退避重启、正常返回即结束、SIGTERM / SIGINT 优雅停机
- 事件循环看门狗：卡死时打印堆栈并退出进程
- 单例循环：`BackgroundLoop(singleton=True)`，基于 PostgreSQL advisory lock
- `session_scope()`：请求之外的数据库会话
- 从 `gateway/app.py` 抽出生命周期与事件订阅，API 与 worker 共用
- loader 校验循环名；架构测试禁止模块内非 `module.py` 代码引用自己的 `worker/`
- `example_a` 增加一个可运行的示例循环
- compose 抽出共享环境变量锚点，给出 worker 服务模板
- 更新 `docs/架构规范.md`

不做：

- 通用任务队列、cron 表达式调度、重试表（规范 §9 的「后台任务队列」仍然不做）
- 跨进程事件、outbox
- 通用租约与心跳（业务独有，放在模块内）
- worker 健康上报接口（看门狗退出 + compose 重启已足够）
- Windows 原生运行 worker
- 任何业务模块（含 tiktok_studio）的 worker 实现

## 关键决策

### 平台托管，模块实现

| 平台负责 | 模块负责 |
|---|---|
| 入口、装载、生命周期钩子 | 循环中的业务逻辑 |
| 逐个托管循环，异常退避重启 | 任务表、状态机、租约、心跳（如需要） |
| 优雅停机 | 幂等、重试、超时策略 |
| 看门狗 | 外部资源池（浏览器、API 客户端） |
| 单例循环的互斥 | 非单例循环在多副本下的并发安全 |
| `session_scope()` | 并发度等配置（用模块配置前缀） |
| 循环命名校验 | 需要系统依赖时提供自己的 worker 镜像 |

### 默认一个模块一个进程

一个模块的阻塞、崩溃、内存泄漏不波及其他模块；每个模块可以单独扩缩容、单独发布；拆分模块时 worker
服务直接搬走。同时允许 `worker a,b` 把多个轻量模块合并到一个进程，`--loops` 把模块内的重循环拆到单独进程，
两者都只改启动命令，不改代码。

### worker 只装载目标模块及其依赖

直接复用 `load_modules(targets)`，它已经递归装入 `depends_on` 并拓扑排序。worker 不注册 registry、不挂路由。
代价是：worker 内发布的事件只有同进程装载的模块能收到。这与「执行只由数据库状态驱动」的原则一致，
拆分模块时语义也不变，因此接受。

### 单例循环用 advisory lock，失锁即停

同一个 worker 服务部署多个副本时，非幂等的循环（发日报、定时清理）会重复执行。`singleton=True` 的循环在运行前
用独立连接获取会话级 `pg_try_advisory_lock(hashtextextended('<模块名>.<循环名>', 0))`，拿不到就每 10 秒重试，
其他副本上的同名循环原地待命。持锁期间每 10 秒在该连接上执行 `SELECT 1`，失败即视为失锁：取消循环并抛出异常，
交给托管层退避重启（重启后重新抢锁）。

这是尽力而为的互斥：连接静默断开到 PostgreSQL 释放锁之间存在短暂窗口，业务上绝对不能重复的操作仍要由模块保证幂等。
不支持事务级连接池（如 PgBouncer transaction 模式），因为会话级锁在其下不成立。每个持锁的单例循环占用一个连接池连接。

### 看门狗是唯一的健康机制

事件循环内一个协程每秒刷新时间戳，独立线程每秒检查。延迟超过 `WORKER_WATCHDOG_TIMEOUT`（默认 60 秒）时，
用 `faulthandler.dump_traceback(all_threads=True)` 打印所有线程堆栈，然后 `os._exit(1)`，由 compose 的
`restart: unless-stopped` 重启。进程退出时数据库连接关闭，单例锁随之释放，其他副本接管。

## 契约（`platforms/contract.py`）

循环名规则同模块名：小写字母、数字、下划线，字母开头。

```python
@dataclass(frozen=True)
class LoopContext:
    module: str
    name: str
    stopping: asyncio.Event
    logger: logging.Logger                     # 名为 worker.<模块名>.<循环名>

    async def sleep(self, seconds: float) -> bool:
        """等待 seconds 秒；期间收到停机信号则提前返回 False，否则返回 True。"""

@dataclass(frozen=True)
class BackgroundLoop:
    name: str                                  # 模块内唯一，全局名 <模块名>.<name>
    run: Callable[[LoopContext], Awaitable[None]]
    stop_timeout: float = 30                   # 停机信号发出后等待退出的上限，超时则取消
    singleton: bool = False                    # 多副本时全局只运行一份

@dataclass(frozen=True)
class ModuleSpec:
    ...
    loops: tuple[BackgroundLoop, ...] = ()
```

循环写法：先做一轮工作再休眠，`ctx.sleep` 返回 False 时退出。

```python
async def report_item_count(ctx: LoopContext) -> None:
    while True:
        async with session_scope() as session:
            ...
        if not await ctx.sleep(30):
            return
```

## 组件

| 文件 | 职责 |
|---|---|
| `platforms/contract.py` | 新增 `LoopContext`、`BackgroundLoop`，`ModuleSpec.loops` |
| `platforms/gateway/loader.py` | `validate_spec` 校验循环名格式与模块内唯一 |
| `platforms/db.py` | 新增 `session_scope()`；`get_session` 改为复用它 |
| `platforms/lifecycle.py` | `subscribe_events(modules)`、`module_lifecycle(modules)`（启动钩子、逆序关闭钩子、释放连接池） |
| `platforms/gateway/app.py` | 改用 `lifecycle.py`，行为不变 |
| `platforms/worker/supervisor.py` | `supervise(loop, ctx)`：异常按 1、2、4…最长 60 秒退避重启；单次运行超过 60 秒后失败则退避重置为 1 秒；正常返回即结束；退避等待可被停机打断 |
| `platforms/worker/singleton.py` | `run_exclusive(ctx, run)`：抢锁、持锁运行、连接检查、失锁抛 `SingletonLockLost` |
| `platforms/worker/watchdog.py` | `Watchdog(timeout, on_timeout)`：`start()` / `stop()` |
| `platforms/worker/runner.py` | `select_loops`、`run_worker`：校验、装载、信号、看门狗、托管、停机 |
| `platforms/config.py` | 新增 `worker_watchdog_timeout: float = 60` |
| `main.py` | 子命令：`api`（默认）、`worker` |

## 运行流程

```
python main.py worker example_a [--loops report_item_count]
  1. 解析目标模块列表；配置了 ENABLED_MODULES 且目标不在其中 → 报错退出
  2. load_modules(targets) → 目标模块 + depends_on 闭包，按依赖排序
  3. select_loops：只取目标模块（不含依赖模块）的循环；--loops 写模块内循环名（不带模块前缀），
     仅在单个目标模块时允许，名字不存在 → 报错；最终没有循环 → 报错
  4. 安装 SIGTERM / SIGINT 处理（设置 stopping）；启动看门狗
  5. module_lifecycle：订阅事件，按顺序执行 on_startup
  6. 每个循环一个 task：supervise(loop, ctx)；singleton 循环的 run 包一层 run_exclusive
  7. 等待：stopping 被设置，或所有循环都已结束
  8. 设置 stopping；每个 task 最多等待自己的 stop_timeout，超时取消
  9. 逆序执行 on_shutdown，dispose_engine；停止看门狗；进程退出码 0
```

## 错误处理

| 情况 | 行为 |
|---|---|
| 循环抛异常 | 记 `logger.exception`，退避后重启，不影响其他循环 |
| 循环正常返回 | 该循环结束，不重启；全部结束后进程正常退出 |
| 单例失锁 | 取消循环，抛 `SingletonLockLost`，走退避重启并重新抢锁 |
| 事件循环卡死 | 看门狗打印堆栈，`os._exit(1)` |
| 停机超时 | 取消对应 task，记 warning |
| `on_startup` 失败 | 已启动的模块逆序关闭，进程以异常退出 |
| 目标模块不存在、不在 `ENABLED_MODULES`、循环名不存在、无循环可跑 | 启动即报错退出，不重试 |

## 模块约定

```
modules/<模块名>/
├─ module.py          MODULE = ModuleSpec(..., loops=LOOPS)
├─ worker/            所有后台逻辑；__init__.py 导出 LOOPS
├─ worker.Dockerfile  可选：需要系统依赖时才提供
└─ config.py          worker 配置也用 <模块名大写>_ 前缀
```

1. 模块内除 `module.py` 和 `worker/` 自身外，不得 import `modules.<模块名>.worker`（架构测试检查）。
2. `worker/` 在 import 时不得产生副作用：不建连接、不开线程、不启动外部进程。API 进程也会 import 它。
3. `on_startup` / `on_shutdown` 会在 API 进程和每个装载了该模块的 worker 进程中各执行一次，必须幂等，且不得启动后台任务。
4. worker 发布的事件只有同进程装载的模块能收到。需要通知其他模块时写自己的状态表，由对方通过 `contract.py` 查询。
5. 非单例循环在多副本下的并发安全由模块保证（如 `FOR UPDATE SKIP LOCKED`）；不能重复执行的循环声明 `singleton=True`。
6. CPU 密集操作放到线程池或子进程，否则会触发看门狗。
7. worker 尽量少同步调用其他模块的 `contract.py`：拆分模块时这些调用要变成远程调用，是拆分的主要成本。

## 示例（`example_a`）

`modules/example_a/worker/__init__.py` 声明 `report_item_count`：每 30 秒用 `session_scope()` 统计
`mod_example_a.item` 行数并写一条 info 日志。`module.py` 通过 `loops=LOOPS` 暴露。
本地运行 `python main.py worker example_a` 即可看到效果。

## 部署

`deploy/docker-compose.yml` 抽出 `x-backend-env` 锚点，`migrate`、`server` 共用，保证 `ENABLED_MODULES` 等配置一致。
文件中给出注释形式的 worker 服务模板，不默认启用，避免示例 worker 进入生产：

```yaml
# worker-<模块名>:
#   build: *server-build             # 有 worker.Dockerfile 的模块改用自己的镜像
#   command: ["python", "main.py", "worker", "<模块名>"]
#   restart: unless-stopped
#   stop_grace_period: 60s           # 大于该模块循环的最大 stop_timeout
#   environment:
#     <<: *backend-env
#     POSTGRES_POOL_SIZE: 3          # 每个持锁的单例循环额外占一个连接
#   depends_on:
#     migrate:
#       condition: service_completed_successfully
```

## 命名（规范 §2 新增）

| 项 | 规则 | 示例 |
|---|---|---|
| 后台循环 | `<模块名>.<循环名>`，循环名规则同模块名 | `example_a.report_item_count` |
| worker 服务 | `worker-<模块名>` | `worker-example_a` |
| 循环日志 | `worker.<模块名>.<循环名>` | `worker.example_a.report_item_count` |

## 测试

| 文件 | 覆盖 |
|---|---|
| `tests/platforms/test_loader.py` | 循环名格式非法、模块内重名被拒绝 |
| `tests/platforms/test_worker_supervisor.py` | 异常后重启、正常返回结束、退避等待被停机打断、`LoopContext.sleep` 返回值 |
| `tests/platforms/test_worker_watchdog.py` | 事件循环被阻塞超过阈值时回调被调用；正常时不调用 |
| `tests/platforms/test_worker_runner.py` | 只选目标模块的循环、`--loops` 过滤与报错、`ENABLED_MODULES` 校验、收到停机后退出、停机超时取消、生命周期钩子执行顺序 |
| `tests/platforms/test_worker_singleton.py`（db） | 两个同名单例只有一个运行；前者结束后后者接管 |
| `tests/platforms/test_db.py`（db） | `session_scope` 正常提交、异常回滚 |
| `tests/platforms/test_architecture.py` | 模块内非 `module.py` 代码不得引用自己的 `worker/` |
| `tests/modules/example_a/test_worker.py`（db） | 示例循环跑一轮后退出并输出条目数 |

标记 `db` 的用例需要 PostgreSQL。当前 WSL 未开启 Docker Desktop 集成，这些用例在本机会跳过，需在可用数据库的环境补跑。

## 规范更新（`docs/架构规范.md`）

- §1 目录结构：`lifecycle.py`、`worker/`
- §2 命名表：上表三行
- §3 模块边界：事件只在进程内派发；worker 由数据库状态驱动；模块约定 1–7
- §6 新增模块：有后台逻辑时在 `worker/` 中声明 `LOOPS`
- §7 本地开发：`python main.py worker <模块名>`
- §8 部署：worker 服务模板、单副本与单例的关系
- §9：后台循环托管已支持，通用任务队列仍不做
