# Worker 框架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为框架补上通用 worker 骨架：模块用 `ModuleSpec.loops` 声明后台循环，`python main.py worker <模块>` 托管运行。

**Architecture:** 平台只负责进程骨架（装载、托管、停机、看门狗、单例锁、`session_scope`），后台逻辑全部在模块的 `worker/` 中实现。worker 进程只装载目标模块及其 `depends_on` 闭包，复用 API 进程的生命周期代码。

**Tech Stack:** Python 3.14、asyncio、SQLAlchemy 2.1 async + psycopg 3、PostgreSQL 17 advisory lock、pytest-asyncio。

**Spec:** `docs/superpowers/specs/2026-10-04-worker-framework-design.md`

## Global Constraints

- 运行平台仅 Linux；不做 Windows 兼容分支。
- 平台层不得 import `modules`（架构测试已检查）。
- 循环名规则同模块名：`^[a-z][a-z0-9_]*$`，模块内唯一。
- 循环全局名 `<模块名>.<循环名>`；日志名 `worker.<模块名>.<循环名>`；worker 服务名 `worker-<模块名>`。
- 退避：初始 1 秒，翻倍，上限 60 秒；单次运行 ≥ 上限后失败则重置为初始值。
- 单例锁：`pg_try_advisory_lock(hashtextextended('<模块名>.<循环名>', 0))`，抢锁重试与持锁连接检查间隔均为 10 秒。
- 看门狗默认阈值 `WORKER_WATCHDOG_TIMEOUT=60` 秒，超时 `faulthandler.dump_traceback(all_threads=True)` 后 `os._exit(1)`。
- `BackgroundLoop.stop_timeout` 默认 30 秒。
- 所有命令在 `server/` 目录、已激活 `.venv`（`source .venv/bin/activate`）下执行；PostgreSQL 由 `deploy` 中的 compose `postgres` 服务提供。
- 注释与日志用中文，风格与现有代码一致；不写解释「这次改了什么」的注释。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `server/platforms/contract.py` | 改 | `LoopContext`、`BackgroundLoop`、`ModuleSpec.loops` |
| `server/platforms/gateway/loader.py` | 改 | 循环名校验 |
| `server/platforms/db.py` | 改 | `session_scope()`；`get_session` 复用 |
| `server/platforms/lifecycle.py` | 新 | `subscribe_events`、`module_lifecycle` |
| `server/platforms/gateway/app.py` | 改 | 改用 `lifecycle.py` |
| `server/platforms/worker/__init__.py` | 新 | 包说明 |
| `server/platforms/worker/supervisor.py` | 新 | `supervise` |
| `server/platforms/worker/watchdog.py` | 新 | `Watchdog` |
| `server/platforms/worker/singleton.py` | 新 | `run_exclusive`、`SingletonLockLost` |
| `server/platforms/worker/runner.py` | 新 | `WorkerConfigError`、`select_loops`、`run_worker` |
| `server/platforms/config.py` | 改 | `worker_watchdog_timeout` |
| `server/main.py` | 改 | 子命令 `api` / `worker` |
| `server/modules/example_a/service.py` | 改 | `count_items` |
| `server/modules/example_a/worker/__init__.py` | 新 | 示例循环 `report_item_count` |
| `server/modules/example_a/module.py` | 改 | `loops=LOOPS` |
| `server/tests/platforms/test_loader.py` | 改 | 循环名校验用例 |
| `server/tests/platforms/test_db.py` | 新 | `session_scope` 用例（db） |
| `server/tests/platforms/test_gateway.py` | 改 | 打桩目标改为 `lifecycle.dispose_engine` |
| `server/tests/platforms/test_worker_supervisor.py` | 新 | 托管与 `LoopContext.sleep` |
| `server/tests/platforms/test_worker_watchdog.py` | 新 | 看门狗 |
| `server/tests/platforms/test_worker_singleton.py` | 新 | 单例锁（db） |
| `server/tests/platforms/test_worker_runner.py` | 新 | 选择、启动校验、停机、CLI |
| `server/tests/platforms/test_architecture.py` | 改 | 禁止非 `module.py` 引用自己的 `worker/` |
| `server/tests/modules/example_a/test_worker.py` | 新 | 示例循环（db） |
| `deploy/docker-compose.yml` | 改 | `x-backend-env` 锚点与 worker 模板 |
| `docs/架构规范.md` | 改 | §1 §2 §3 §6 §7 §8 §9 |

---

### Task 1: 循环契约与 loader 校验

**Files:**
- Modify: `server/platforms/contract.py`
- Modify: `server/platforms/gateway/loader.py:61-64`
- Test: `server/tests/platforms/test_loader.py`
- Test: `server/tests/platforms/test_worker_supervisor.py`（本任务只放 `LoopContext.sleep` 用例）

**Interfaces:**
- Produces:
  - `LoopContext(module: str, name: str, stopping: asyncio.Event, logger: logging.Logger)`，方法 `async sleep(seconds: float) -> bool`
  - `BackgroundLoop(name: str, run: Callable[[LoopContext], Awaitable[None]], stop_timeout: float = 30.0, singleton: bool = False)`
  - `ModuleSpec.loops: tuple[BackgroundLoop, ...] = ()`
  - `LoopRunner = Callable[[LoopContext], Awaitable[None]]`

- [ ] **Step 1: 写失败用例**

在 `server/tests/platforms/test_loader.py` 顶部 import 改为：

```python
from platforms.contract import BackgroundLoop, MenuDef, ModuleSpec, PermissionDef
```

在 `test_rejects_menu_with_missing_parent` 之后追加：

```python
async def _noop(ctx) -> None:
    return None


def test_rejects_invalid_loop_name():
    with pytest.raises(ModuleLoadError, match="循环名"):
        validate_spec(_spec(loops=(BackgroundLoop("Bad-Name", _noop),)), "demo")


def test_rejects_duplicate_loop_names():
    loops = (BackgroundLoop("sync", _noop), BackgroundLoop("sync", _noop))
    with pytest.raises(ModuleLoadError, match="重复的循环名"):
        validate_spec(_spec(loops=loops), "demo")
```

新建 `server/tests/platforms/test_worker_supervisor.py`：

```python
"""后台循环托管：异常退避重启、正常返回即结束、停机可打断等待。"""

import asyncio
import logging

from platforms.contract import LoopContext


def _ctx(stopping: asyncio.Event | None = None) -> LoopContext:
    return LoopContext("demo", "job", stopping or asyncio.Event(), logging.getLogger("worker.demo.job"))


async def test_sleep_returns_true_after_timeout():
    assert await _ctx().sleep(0.01) is True


async def test_sleep_returns_false_when_stopping():
    stopping = asyncio.Event()
    asyncio.get_running_loop().call_later(0.01, stopping.set)
    assert await _ctx(stopping).sleep(5) is False
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/platforms/test_loader.py tests/platforms/test_worker_supervisor.py -q`
Expected: FAIL，`ImportError: cannot import name 'BackgroundLoop'` / `'LoopContext'`

- [ ] **Step 3: 实现契约**

`server/platforms/contract.py` 整体替换为：

```python
"""模块与平台之间的契约：每个模块在 modules/<模块名>/module.py 中导出 MODULE = ModuleSpec(...)。

ModuleSpec 是模块元信息的唯一来源——路由、权限点、菜单、后台循环都在这里声明一次，
前端不重复维护菜单和权限清单，登录后调 GET /api/modules 取。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import APIRouter

LifecycleHook = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class PermissionDef:
    code: str                       # 格式 <模块名>:<资源>:<动作>，如 example:item:create
    name: str


@dataclass(frozen=True)
class MenuDef:
    title: str
    path: str                       # 前端路由，必须以 /<模块名> 开头
    icon: str = ""
    order: int = 0
    permission: str | None = None   # 命中该权限码的用户才能看到，须在本模块 permissions 中声明
    parent: str | None = None       # 父菜单的 path，为空表示一级菜单


@dataclass(frozen=True)
class LoopContext:
    """平台传给后台循环的运行上下文。"""
    module: str
    name: str
    stopping: asyncio.Event                 # 收到停机信号后被设置，循环应尽快退出
    logger: logging.Logger                  # 名为 worker.<模块名>.<循环名>

    async def sleep(self, seconds: float) -> bool:
        """等待 seconds 秒；期间收到停机信号则提前返回 False，否则返回 True。"""
        try:
            await asyncio.wait_for(self.stopping.wait(), seconds)
        except TimeoutError:
            return True
        return False


LoopRunner = Callable[[LoopContext], Awaitable[None]]


@dataclass(frozen=True)
class BackgroundLoop:
    name: str                               # 模块内唯一，全局名为 <模块名>.<name>
    run: LoopRunner                         # 抛异常会被退避重启，正常返回视为该循环结束
    stop_timeout: float = 30.0              # 停机信号发出后等待退出的上限，超时则取消
    singleton: bool = False                 # 多副本部署时全局只运行一份（PostgreSQL advisory lock）


@dataclass(frozen=True)
class ModuleSpec:
    name: str                                               # 必须与模块目录名一致，路由挂到 /api/<name>
    title: str                                              # 菜单分组名
    version: str = "0.1.0"
    depends_on: tuple[str, ...] = ()                        # 依赖的其他模块名，禁止成环
    router: APIRouter | None = None
    permissions: tuple[PermissionDef, ...] = ()
    menus: tuple[MenuDef, ...] = ()
    on_startup: LifecycleHook | None = None                 # 进程启动时按加载顺序调用（API 与每个 worker 各一次）
    on_shutdown: LifecycleHook | None = None                # 进程关闭时按加载的逆序调用
    subscriptions: dict[str, tuple[Callable, ...]] = field(default_factory=dict)  # 事件名 -> 处理函数
    loops: tuple[BackgroundLoop, ...] = ()                  # 后台循环，只在 python main.py worker 中运行
```

- [ ] **Step 4: 实现 loader 校验**

`server/platforms/gateway/loader.py` 中 `validate_spec` 末尾（事件名校验之后）追加：

```python
    loop_names = [loop.name for loop in spec.loops]
    for loop_name in loop_names:
        if not MODULE_NAME_PATTERN.match(loop_name):
            raise ModuleLoadError(f"循环名 {loop_name!r} 不合规：只允许小写字母、数字、下划线，且以字母开头")
    if len(set(loop_names)) != len(loop_names):
        raise ModuleLoadError(f"模块 {spec.name} 存在重复的循环名")
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/platforms/test_loader.py tests/platforms/test_worker_supervisor.py -q`
Expected: PASS

- [ ] **Step 6: 全量回归并提交**

Run: `pytest -q`
Expected: 全部通过

```bash
git add server/platforms/contract.py server/platforms/gateway/loader.py server/tests/platforms/test_loader.py server/tests/platforms/test_worker_supervisor.py
git commit -m "feat(platform): add BackgroundLoop contract and loop name validation"
```

---

### Task 2: `session_scope()` 与生命周期抽取

**Files:**
- Modify: `server/platforms/db.py`
- Create: `server/platforms/lifecycle.py`
- Modify: `server/platforms/gateway/app.py`
- Modify: `server/tests/platforms/test_gateway.py:48-75`
- Test: `server/tests/platforms/test_db.py`

**Interfaces:**
- Produces:
  - `platforms.db.session_scope() -> AbstractAsyncContextManager[AsyncSession]`
  - `platforms.lifecycle.subscribe_events(modules: list[ModuleSpec]) -> None`
  - `platforms.lifecycle.module_lifecycle(modules: list[ModuleSpec]) -> AbstractAsyncContextManager[None]`（退出时调用 `platforms.lifecycle.dispose_engine`）

- [ ] **Step 1: 写失败用例**

新建 `server/tests/platforms/test_db.py`：

```python
"""请求之外的数据库会话：正常结束提交，抛异常回滚。"""

from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from platforms.auth.models import Role
from platforms.db import session_scope

pytestmark = pytest.mark.db


async def test_session_scope_commits_on_success(db_ready):
    code = f"scope_{uuid4().hex[:12]}"
    async with session_scope() as session:
        session.add(Role(code=code, name="提交"))

    async with session_scope() as session:
        assert await session.scalar(select(Role).where(Role.code == code)) is not None
        await session.execute(delete(Role).where(Role.code == code))


async def test_session_scope_rolls_back_on_error(db_ready):
    code = f"scope_{uuid4().hex[:12]}"
    with pytest.raises(RuntimeError):
        async with session_scope() as session:
            session.add(Role(code=code, name="回滚"))
            await session.flush()
            raise RuntimeError("中断")

    async with session_scope() as session:
        assert await session.scalar(select(Role).where(Role.code == code)) is None
```

修改 `server/tests/platforms/test_gateway.py`：import 区把

```python
from platforms.gateway import app as gateway_app
```

改为

```python
from platforms import lifecycle
from platforms.gateway import app as gateway_app
```

并把 `test_shutdown_continues_after_hook_failure` 中的

```python
    monkeypatch.setattr(gateway_app, "dispose_engine", dispose)
```

改为

```python
    monkeypatch.setattr(lifecycle, "dispose_engine", dispose)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/platforms/test_db.py tests/platforms/test_gateway.py -q`
Expected: FAIL，`ImportError: cannot import name 'session_scope'` 与 `cannot import name 'lifecycle'`

- [ ] **Step 3: 实现 `session_scope`**

`server/platforms/db.py`：import 区加入

```python
from contextlib import asynccontextmanager
```

把 `get_session` 整体替换为：

```python
@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """请求之外的数据库会话（后台循环、脚本）：正常结束时提交，抛异常时回滚。"""
    get_engine()
    assert _session_factory is not None
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：一个请求一个事务，正常返回时提交，抛异常时回滚。"""
    async with session_scope() as session:
        yield session
```

- [ ] **Step 4: 新建 `server/platforms/lifecycle.py`**

```python
"""模块生命周期：API 与 worker 进程共用的事件订阅、启动与关闭流程。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from platforms import events
from platforms.contract import ModuleSpec
from platforms.db import dispose_engine

logger = logging.getLogger("platform.lifecycle")


def subscribe_events(modules: list[ModuleSpec]) -> None:
    """按已加载模块重建进程内的事件订阅。"""
    events.clear()
    for spec in modules:
        for event, handlers in spec.subscriptions.items():
            for handler in handlers:
                events.subscribe(event, handler)


@asynccontextmanager
async def module_lifecycle(modules: list[ModuleSpec]) -> AsyncIterator[None]:
    """按加载顺序执行 on_startup；退出时逆序执行 on_shutdown，最后释放连接池。"""
    started: list[ModuleSpec] = []
    try:
        for spec in modules:
            if spec.on_startup:
                await spec.on_startup()
            started.append(spec)
            logger.info("模块已启动：%s", spec.name)
        yield
    finally:
        for spec in reversed(started):
            if spec.on_shutdown:
                try:
                    await spec.on_shutdown()
                except Exception:
                    logger.exception("模块关闭失败：%s", spec.name)
        await dispose_engine()
```

- [ ] **Step 5: `app.py` 改用 lifecycle**

`server/platforms/gateway/app.py`：

1. 删除 `import logging`、`from platforms import events, registry` 改为 `from platforms import registry`，删除 `from platforms.db import dispose_engine`，删除 `logger = logging.getLogger("platform.gateway")`。
2. 新增 import：`from platforms.lifecycle import module_lifecycle, subscribe_events`
3. `_lifespan` 替换为：

```python
def _lifespan(modules: list[ModuleSpec]):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with module_lifecycle(modules):
            yield

    return lifespan
```

4. `create_app` 中

```python
    events.clear()
    for spec in modules:
        for event, handlers in spec.subscriptions.items():
            for handler in handlers:
                events.subscribe(event, handler)
```

替换为

```python
    subscribe_events(modules)
```

模块顶部 docstring 保持不变。

- [ ] **Step 6: 运行确认通过**

Run: `pytest tests/platforms/test_db.py tests/platforms/test_gateway.py tests/modules/example_a -q`
Expected: PASS

- [ ] **Step 7: 全量回归、lint 并提交**

Run: `pytest -q && ruff check platforms tests`
Expected: 全部通过，ruff 无报错

```bash
git add server/platforms/db.py server/platforms/lifecycle.py server/platforms/gateway/app.py server/tests/platforms/test_db.py server/tests/platforms/test_gateway.py
git commit -m "refactor(platform): extract module lifecycle and add session_scope"
```

---

### Task 3: 循环托管 `supervise`

**Files:**
- Create: `server/platforms/worker/__init__.py`
- Create: `server/platforms/worker/supervisor.py`
- Test: `server/tests/platforms/test_worker_supervisor.py`

**Interfaces:**
- Consumes: `LoopContext`、`LoopRunner`（Task 1）
- Produces: `async supervise(run: LoopRunner, ctx: LoopContext, *, initial_backoff: float = 1.0, max_backoff: float = 60.0) -> None`，除 `CancelledError` 外不向外抛异常

- [ ] **Step 1: 写失败用例**

在 `server/tests/platforms/test_worker_supervisor.py` 的 import 区追加：

```python
from platforms.worker.supervisor import supervise
```

文件末尾追加：

```python
async def test_restarts_after_exception():
    calls = 0

    async def run(ctx):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("boom")

    await asyncio.wait_for(supervise(run, _ctx(), initial_backoff=0.01, max_backoff=0.05), 2)
    assert calls == 3


async def test_normal_return_is_not_restarted():
    calls = 0

    async def run(ctx):
        nonlocal calls
        calls += 1

    await asyncio.wait_for(supervise(run, _ctx(), initial_backoff=0.01), 2)
    assert calls == 1


async def test_stop_interrupts_backoff():
    stopping = asyncio.Event()

    async def run(ctx):
        stopping.set()
        raise RuntimeError("boom")

    await asyncio.wait_for(supervise(run, _ctx(stopping), initial_backoff=10), 1)


async def test_does_not_start_when_already_stopping():
    stopping = asyncio.Event()
    stopping.set()
    calls = 0

    async def run(ctx):
        nonlocal calls
        calls += 1

    await supervise(run, _ctx(stopping))
    assert calls == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/platforms/test_worker_supervisor.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.worker'`

- [ ] **Step 3: 实现**

`server/platforms/worker/__init__.py`：

```python
"""worker 进程骨架：托管模块通过 ModuleSpec.loops 声明的后台循环。"""
```

`server/platforms/worker/supervisor.py`：

```python
"""单个后台循环的托管：抛异常时退避重启，正常返回即结束，退避等待可被停机打断。"""

import time

from platforms.contract import LoopContext, LoopRunner


async def supervise(
    run: LoopRunner,
    ctx: LoopContext,
    *,
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
) -> None:
    backoff = initial_backoff
    while not ctx.stopping.is_set():
        started = time.monotonic()
        try:
            await run(ctx)
            ctx.logger.info("循环已结束")
            return
        except Exception:
            if time.monotonic() - started >= max_backoff:
                backoff = initial_backoff
            ctx.logger.exception("循环异常退出，%.1f 秒后重启", backoff)
        if not await ctx.sleep(backoff):
            return
        backoff = min(backoff * 2, max_backoff)
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/platforms/test_worker_supervisor.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add server/platforms/worker/__init__.py server/platforms/worker/supervisor.py server/tests/platforms/test_worker_supervisor.py
git commit -m "feat(worker): supervise loops with exponential backoff"
```

---

### Task 4: 事件循环看门狗

**Files:**
- Create: `server/platforms/worker/watchdog.py`
- Test: `server/tests/platforms/test_worker_watchdog.py`

**Interfaces:**
- Produces: `Watchdog(timeout: float, on_timeout: Callable[[], None] = _exit_process)`；`start() -> None`（须在运行中的事件循环内调用）；`async stop() -> None`

- [ ] **Step 1: 写失败用例**

新建 `server/tests/platforms/test_worker_watchdog.py`：

```python
"""看门狗：事件循环被阻塞超过阈值时触发，正常运行时不触发。"""

import asyncio
import threading
import time

from platforms.worker.watchdog import Watchdog


async def test_fires_when_event_loop_is_blocked():
    fired = threading.Event()
    watchdog = Watchdog(0.2, on_timeout=fired.set)
    watchdog.start()
    try:
        time.sleep(0.6)
        assert fired.wait(1)
    finally:
        await watchdog.stop()


async def test_does_not_fire_when_event_loop_is_healthy():
    fired = threading.Event()
    watchdog = Watchdog(0.2, on_timeout=fired.set)
    watchdog.start()
    try:
        await asyncio.sleep(0.6)
        assert not fired.is_set()
    finally:
        await watchdog.stop()
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/platforms/test_worker_watchdog.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.worker.watchdog'`

- [ ] **Step 3: 实现**

`server/platforms/worker/watchdog.py`：

```python
"""事件循环看门狗：循环卡死时打印所有线程堆栈并退出进程，交给 compose / systemd 重启。

卡死的事件循环里，asyncio 的超时也不会触发，只能由独立线程从外部判定。
进程退出后数据库连接随之关闭，持有的单例锁会被释放，其他副本得以接管。
"""

import asyncio
import faulthandler
import logging
import os
import sys
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("platform.worker")


def _exit_process() -> None:
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
    os._exit(1)


class Watchdog:
    def __init__(self, timeout: float, on_timeout: Callable[[], None] = _exit_process):
        self._timeout = timeout
        self._on_timeout = on_timeout
        self._interval = min(1.0, timeout / 4)
        self._last_tick = time.monotonic()
        self._stopped = threading.Event()
        self._tick_task: asyncio.Task | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """在运行中的事件循环内调用。"""
        self._last_tick = time.monotonic()
        self._tick_task = asyncio.get_running_loop().create_task(self._tick())
        self._thread = threading.Thread(target=self._watch, name="worker-watchdog", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._stopped.set()
        if self._tick_task is not None:
            self._tick_task.cancel()
            await asyncio.gather(self._tick_task, return_exceptions=True)
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join)

    async def _tick(self) -> None:
        while True:
            self._last_tick = time.monotonic()
            await asyncio.sleep(self._interval)

    def _watch(self) -> None:
        while not self._stopped.wait(self._interval):
            lag = time.monotonic() - self._last_tick
            if lag > self._timeout:
                logger.critical("事件循环已阻塞 %.1f 秒，超过看门狗阈值 %.1f 秒，进程退出", lag, self._timeout)
                self._on_timeout()
                return
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/platforms/test_worker_watchdog.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add server/platforms/worker/watchdog.py server/tests/platforms/test_worker_watchdog.py
git commit -m "feat(worker): add event loop watchdog"
```

---

### Task 5: 单例循环 `run_exclusive`

**Files:**
- Create: `server/platforms/worker/singleton.py`
- Test: `server/tests/platforms/test_worker_singleton.py`

**Interfaces:**
- Consumes: `LoopContext`、`LoopRunner`（Task 1）；`platforms.db.get_engine`
- Produces:
  - `class SingletonLockLost(Exception)`
  - `async run_exclusive(ctx: LoopContext, run: LoopRunner, *, retry_interval: float = 10.0, check_interval: float = 10.0) -> None`：拿到锁后运行 `run(ctx)` 并在其返回后释放锁；等待期间收到停机则直接返回；持锁连接失效则取消 `run` 并抛 `SingletonLockLost`

- [ ] **Step 1: 写失败用例**

新建 `server/tests/platforms/test_worker_singleton.py`：

```python
"""单例循环：同名循环全局只有一份在运行，持锁连接失效时立即停止。"""

import asyncio
import logging

import pytest
from sqlalchemy import text

from platforms.contract import LoopContext
from platforms.db import session_scope
from platforms.worker.singleton import SingletonLockLost, run_exclusive

pytestmark = pytest.mark.db

FAST = {"retry_interval": 0.05, "check_interval": 0.05}


def _ctx(stopping: asyncio.Event, name: str) -> LoopContext:
    return LoopContext("worker_test", name, stopping, logging.getLogger(f"worker.worker_test.{name}"))


async def test_only_one_holder_runs_at_a_time(db_ready):
    stopping = asyncio.Event()
    release = asyncio.Event()
    runs = 0

    async def body(ctx):
        nonlocal runs
        runs += 1
        await release.wait()

    first = asyncio.create_task(run_exclusive(_ctx(stopping, "exclusive"), body, **FAST))
    second = asyncio.create_task(run_exclusive(_ctx(stopping, "exclusive"), body, **FAST))
    await asyncio.sleep(0.3)
    assert runs == 1

    release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 2)
    assert runs == 2


async def test_waiting_holder_returns_on_stop(db_ready):
    release = asyncio.Event()
    waiting_stop = asyncio.Event()
    ran = []

    async def holder(ctx):
        await release.wait()

    async def waiter(ctx):
        ran.append(ctx.name)

    first = asyncio.create_task(run_exclusive(_ctx(asyncio.Event(), "stop_wait"), holder, **FAST))
    await asyncio.sleep(0.2)
    second = asyncio.create_task(run_exclusive(_ctx(waiting_stop, "stop_wait"), waiter, **FAST))
    await asyncio.sleep(0.2)
    waiting_stop.set()
    await asyncio.wait_for(second, 1)
    assert ran == []

    release.set()
    await asyncio.wait_for(first, 1)


async def test_lock_loss_cancels_run(db_ready):
    cancelled = asyncio.Event()

    async def body(ctx):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(run_exclusive(_ctx(asyncio.Event(), "lock_loss"), body, **FAST))
    await asyncio.sleep(0.2)
    async with session_scope() as session:
        await session.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_locks "
                "WHERE locktype = 'advisory' AND granted AND pid <> pg_backend_pid()"
            )
        )

    with pytest.raises(SingletonLockLost):
        await asyncio.wait_for(task, 2)
    assert cancelled.is_set()
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/platforms/test_worker_singleton.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.worker.singleton'`（若显示 skipped，说明 PostgreSQL 未启动，先 `cd ../deploy && docker compose -p lancha up -d postgres`）

- [ ] **Step 3: 实现**

`server/platforms/worker/singleton.py`：

```python
"""单例循环：用 PostgreSQL 会话级 advisory lock 保证同名循环全局只运行一份。

锁绑定在一条独占连接上，连接断开即释放。持锁期间定期在该连接上探活，探活失败视为失锁，
立即取消循环，避免与接管的副本同时运行。连接静默断开到服务端释放锁之间仍有短暂窗口，
绝对不能重复的业务操作仍需模块自己保证幂等。不支持事务级连接池（如 PgBouncer transaction 模式）。
"""

import asyncio
import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from platforms.contract import LoopContext, LoopRunner
from platforms.db import get_engine

_TRY_LOCK = text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))")
_UNLOCK = text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))")
_PING = text("SELECT 1")


class SingletonLockLost(Exception):
    """持锁连接失效，锁可能已被其他副本获得。"""


async def run_exclusive(
    ctx: LoopContext,
    run: LoopRunner,
    *,
    retry_interval: float = 10.0,
    check_interval: float = 10.0,
) -> None:
    key = f"{ctx.module}.{ctx.name}"
    waiting_logged = False
    while True:
        async with get_engine().connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            if (await conn.execute(_TRY_LOCK, {"key": key})).scalar():
                ctx.logger.info("已获得单例锁：%s", key)
                try:
                    await _run_locked(conn, ctx, run, check_interval)
                finally:
                    with contextlib.suppress(Exception):
                        await conn.execute(_UNLOCK, {"key": key})
                return
        if not waiting_logged:
            ctx.logger.info("单例锁 %s 由其他副本持有，进入待命", key)
            waiting_logged = True
        if not await ctx.sleep(retry_interval):
            return


async def _run_locked(conn: AsyncConnection, ctx: LoopContext, run: LoopRunner, check_interval: float) -> None:
    task = asyncio.create_task(run(ctx))
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=check_interval)
            if done:
                return task.result()
            try:
                await conn.execute(_PING)
            except Exception as exc:
                raise SingletonLockLost(f"单例锁连接失效：{ctx.module}.{ctx.name}") from exc
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/platforms/test_worker_singleton.py -q`
Expected: PASS（3 passed，不能是 skipped）

- [ ] **Step 5: 全量回归并提交**

Run: `pytest -q`
Expected: 全部通过（`test_lock_loss_cancels_run` 会终止测试库中其他持有 advisory lock 的连接，测试库只供测试使用，不影响开发库）

```bash
git add server/platforms/worker/singleton.py server/tests/platforms/test_worker_singleton.py
git commit -m "feat(worker): add advisory-lock singleton loops"
```

---

### Task 6: worker 运行器与启动入口

**Files:**
- Create: `server/platforms/worker/runner.py`
- Modify: `server/platforms/config.py`
- Modify: `server/main.py`
- Test: `server/tests/platforms/test_worker_runner.py`

**Interfaces:**
- Consumes: `supervise`（Task 3）、`Watchdog`（Task 4）、`run_exclusive`（Task 5）、`module_lifecycle` / `subscribe_events`（Task 2）、`load_modules`
- Produces:
  - `class WorkerConfigError(Exception)`
  - `select_loops(modules: list[ModuleSpec], targets: list[str], loop_names: list[str]) -> list[tuple[str, BackgroundLoop]]`
  - `async run_worker(settings: Settings, targets: Sequence[str], loop_names: Sequence[str] = (), package: str = "modules") -> None`
  - `Settings.worker_watchdog_timeout: float = 60.0`
  - `main._parse_args(argv: list[str]) -> argparse.Namespace`（`command` 为 `None` / `"api"` / `"worker"`；worker 有 `modules: list[str]`、`loops: list[str]`）

- [ ] **Step 1: 写失败用例**

新建 `server/tests/platforms/test_worker_runner.py`：

```python
"""worker 运行器：循环选择、启动校验、停机流程与命令行解析。"""

import asyncio
import os
import signal

import pytest

from main import _parse_args
from platforms import events, lifecycle
from platforms.config import Settings
from platforms.contract import BackgroundLoop, ModuleSpec
from platforms.worker import runner
from platforms.worker.runner import WorkerConfigError, run_worker, select_loops


async def _noop(ctx) -> None:
    return None


def _spec(name: str, loops=(), **kwargs) -> ModuleSpec:
    return ModuleSpec(name=name, title=name, loops=loops, **kwargs)


def _settings(**kwargs) -> Settings:
    return Settings(**{"enabled_modules": [], **kwargs})


@pytest.fixture
def install_modules(monkeypatch):
    async def dispose():
        return None

    monkeypatch.setattr(lifecycle, "dispose_engine", dispose)

    def install(*specs: ModuleSpec) -> None:
        monkeypatch.setattr(runner, "load_modules", lambda names, package="modules": list(specs))

    yield install
    events.clear()


def _modules() -> list[ModuleSpec]:
    return [
        _spec("base", (BackgroundLoop("base_job", _noop),)),
        _spec("demo", (BackgroundLoop("a", _noop), BackgroundLoop("b", _noop)), depends_on=("base",)),
    ]


def test_selects_only_target_module_loops():
    selected = select_loops(_modules(), ["demo"], [])
    assert [(module, loop.name) for module, loop in selected] == [("demo", "a"), ("demo", "b")]


def test_filters_by_loop_names():
    selected = select_loops(_modules(), ["demo"], ["b"])
    assert [(module, loop.name) for module, loop in selected] == [("demo", "b")]


def test_rejects_unknown_loop_name():
    with pytest.raises(WorkerConfigError, match="不存在循环"):
        select_loops(_modules(), ["demo"], ["missing"])


def test_rejects_loop_names_with_multiple_modules():
    with pytest.raises(WorkerConfigError, match="单个模块"):
        select_loops(_modules(), ["demo", "base"], ["a"])


def test_rejects_module_without_loops():
    with pytest.raises(WorkerConfigError, match="没有可运行"):
        select_loops([_spec("empty")], ["empty"], [])


async def test_refuses_module_not_in_enabled_modules():
    with pytest.raises(WorkerConfigError, match="ENABLED_MODULES"):
        await run_worker(_settings(enabled_modules=["other"]), ["demo"])


async def test_runs_lifecycle_around_loops_and_exits_when_all_finish(install_modules):
    calls = []

    async def startup():
        calls.append("startup")

    async def shutdown():
        calls.append("shutdown")

    async def job(ctx):
        calls.append(f"{ctx.module}.{ctx.name}")

    install_modules(_spec("demo", (BackgroundLoop("job", job),), on_startup=startup, on_shutdown=shutdown))
    await asyncio.wait_for(run_worker(_settings(), ["demo"]), 2)
    assert calls == ["startup", "demo.job", "shutdown"]


async def test_sigterm_stops_loops_gracefully(install_modules):
    stopped = []

    async def job(ctx):
        while await ctx.sleep(10):
            pass
        stopped.append(ctx.name)

    install_modules(_spec("demo", (BackgroundLoop("job", job),)))
    asyncio.get_running_loop().call_later(0.1, os.kill, os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(run_worker(_settings(), ["demo"]), 2)
    assert stopped == ["job"]


async def test_loop_ignoring_stop_is_cancelled_after_timeout(install_modules):
    cancelled = []

    async def stubborn(ctx):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(ctx.name)
            raise

    install_modules(_spec("demo", (BackgroundLoop("stubborn", stubborn, stop_timeout=0.1),)))
    asyncio.get_running_loop().call_later(0.1, os.kill, os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(run_worker(_settings(), ["demo"]), 2)
    assert cancelled == ["stubborn"]


def test_cli_defaults_to_api():
    assert _parse_args([]).command is None


def test_cli_parses_worker_arguments():
    args = _parse_args(["worker", "a,b", "--loops", "x, y"])
    assert args.command == "worker"
    assert args.modules == ["a", "b"]
    assert args.loops == ["x", "y"]
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/platforms/test_worker_runner.py -q`
Expected: FAIL，`ImportError: cannot import name '_parse_args' from 'main'`

- [ ] **Step 3: 配置项**

`server/platforms/config.py` 在 `postgres_max_overflow` 之后追加：

```python

    # worker 事件循环看门狗阈值（秒）：循环阻塞超过该值即打印堆栈并退出进程，交给 compose 重启
    worker_watchdog_timeout: float = 60.0
```

- [ ] **Step 4: 实现运行器**

`server/platforms/worker/runner.py`：

```python
"""worker 进程：装载目标模块及其依赖，托管目标模块声明的后台循环，处理停机信号。

只装载需要的模块：worker 内发布的事件只有同进程装载的模块能收到，执行应由数据库状态驱动。
"""

import asyncio
import logging
import signal
from collections.abc import Sequence

from platforms.config import Settings
from platforms.contract import BackgroundLoop, LoopContext, LoopRunner, ModuleSpec
from platforms.gateway.loader import load_modules
from platforms.lifecycle import module_lifecycle, subscribe_events
from platforms.worker.singleton import run_exclusive
from platforms.worker.supervisor import supervise
from platforms.worker.watchdog import Watchdog

logger = logging.getLogger("platform.worker")

_STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class WorkerConfigError(Exception):
    """启动参数与模块声明不匹配，worker 拒绝启动。"""


def select_loops(
    modules: list[ModuleSpec], targets: list[str], loop_names: list[str]
) -> list[tuple[str, BackgroundLoop]]:
    """只取目标模块自己的循环（依赖模块的循环不运行）；loop_names 为空表示全部。"""
    if loop_names and len(targets) != 1:
        raise WorkerConfigError("--loops 只能在指定单个模块时使用")
    by_name = {spec.name: spec for spec in modules}
    selected = [(name, loop) for name in targets for loop in by_name[name].loops]
    if loop_names:
        available = {loop.name for _, loop in selected}
        unknown = [name for name in loop_names if name not in available]
        if unknown:
            raise WorkerConfigError(f"模块 {targets[0]} 中不存在循环：{unknown}，可用循环：{sorted(available)}")
        selected = [(module, loop) for module, loop in selected if loop.name in loop_names]
    if not selected:
        raise WorkerConfigError(f"模块 {targets} 没有可运行的后台循环")
    return selected


async def run_worker(
    settings: Settings, targets: Sequence[str], loop_names: Sequence[str] = (), package: str = "modules"
) -> None:
    if not targets:
        raise WorkerConfigError("至少指定一个模块")
    if settings.enabled_modules:
        disabled = [name for name in targets if name not in settings.enabled_modules]
        if disabled:
            raise WorkerConfigError(f"模块 {disabled} 不在 ENABLED_MODULES 中，拒绝启动")
    modules = load_modules(list(targets), package)
    selected = select_loops(modules, list(targets), list(loop_names))

    stopping = asyncio.Event()
    event_loop = asyncio.get_running_loop()
    for sig in _STOP_SIGNALS:
        event_loop.add_signal_handler(sig, stopping.set)
    watchdog = Watchdog(settings.worker_watchdog_timeout)
    watchdog.start()
    try:
        subscribe_events(modules)
        async with module_lifecycle(modules):
            await _run_loops(selected, stopping)
    finally:
        await watchdog.stop()
        for sig in _STOP_SIGNALS:
            event_loop.remove_signal_handler(sig)


def _entry(loop: BackgroundLoop) -> LoopRunner:
    if not loop.singleton:
        return loop.run

    async def exclusive(ctx: LoopContext) -> None:
        await run_exclusive(ctx, loop.run)

    return exclusive


async def _run_loops(selected: list[tuple[str, BackgroundLoop]], stopping: asyncio.Event) -> None:
    tasks: dict[asyncio.Task, BackgroundLoop] = {}
    for module, loop in selected:
        ctx = LoopContext(module, loop.name, stopping, logging.getLogger(f"worker.{module}.{loop.name}"))
        tasks[asyncio.create_task(supervise(_entry(loop), ctx), name=f"{module}.{loop.name}")] = loop
    logger.info("worker 已启动：%s", ", ".join(task.get_name() for task in tasks))

    stop_wait = asyncio.create_task(stopping.wait())
    pending = set(tasks)
    while pending and not stopping.is_set():
        done, _ = await asyncio.wait(pending | {stop_wait}, return_when=asyncio.FIRST_COMPLETED)
        pending -= done
    stop_wait.cancel()
    stopping.set()
    if pending:
        logger.info("收到停机信号，等待 %d 个循环退出", len(pending))
    await asyncio.gather(*(_stop(task, tasks[task].stop_timeout) for task in pending))
    logger.info("worker 已停止")


async def _stop(task: asyncio.Task, timeout: float) -> None:
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.warning("循环 %s 未在 %.1f 秒内退出，已取消", task.get_name(), timeout)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
```

- [ ] **Step 5: 启动入口**

`server/main.py` 整体替换为：

```python
"""统一启动入口：在 server 目录执行。

python main.py                                   启动 API 网关（等同 python main.py api）
python main.py worker <模块>[,<模块>]            运行这些模块声明的全部后台循环
python main.py worker <模块> --loops a,b         只运行该模块内的部分循环
"""

import argparse
import asyncio
import logging
import sys

import uvicorn

from platforms.config import Settings, get_settings
from platforms.gateway.loader import ModuleLoadError
from platforms.worker.runner import WorkerConfigError, run_worker


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python main.py")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("api", help="启动 API 网关（默认）")
    worker = commands.add_parser("worker", help="运行模块声明的后台循环")
    worker.add_argument("modules", type=_csv, help="模块名，多个用逗号分隔")
    worker.add_argument("--loops", type=_csv, default=[], help="只运行模块内的这些循环，逗号分隔；仅限单个模块")
    return parser.parse_args(argv)


def _run_api(settings: Settings) -> None:
    uvicorn.run(
        "platforms.gateway.app:create_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        # psycopg 异步不支持 Windows 默认的 ProactorEventLoop，统一使用 SelectorEventLoop
        loop="asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto",
    )


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    if args.command == "worker":
        try:
            asyncio.run(run_worker(settings, args.modules, args.loops))
        except (WorkerConfigError, ModuleLoadError) as exc:
            sys.exit(f"worker 启动失败：{exc}")
    else:
        _run_api(settings)
```

- [ ] **Step 6: 运行确认通过**

Run: `pytest tests/platforms/test_worker_runner.py -q`
Expected: PASS（12 passed）

- [ ] **Step 7: 全量回归、lint 并提交**

Run: `pytest -q && ruff check main.py platforms tests`
Expected: 全部通过，ruff 无报错

```bash
git add server/platforms/worker/runner.py server/platforms/config.py server/main.py server/tests/platforms/test_worker_runner.py
git commit -m "feat(worker): add worker runner and main.py worker command"
```

---

### Task 7: 架构约束与 `example_a` 示例循环

**Files:**
- Modify: `server/tests/platforms/test_architecture.py`
- Modify: `server/modules/example_a/service.py`
- Create: `server/modules/example_a/worker/__init__.py`
- Modify: `server/modules/example_a/module.py`
- Test: `server/tests/modules/example_a/test_worker.py`

**Interfaces:**
- Consumes: `BackgroundLoop`、`LoopContext`（Task 1）、`session_scope`（Task 2）、`python main.py worker`（Task 6）
- Produces: `modules.example_a.service.count_items(session) -> int`；`modules.example_a.worker.LOOPS`、`report_item_count(ctx)`

- [ ] **Step 1: 写架构用例**

`server/tests/platforms/test_architecture.py` 在 `test_modules_only_import_each_other_contract` 之后追加：

```python
def test_only_module_py_imports_own_worker():
    """后台逻辑只经 ModuleSpec.loops 交给 worker 进程，API 等代码直接引用 worker/ 就等于在 API 里执行后台逻辑。"""
    offenders = []
    for name in discover_module_names():
        root = SERVER / "modules" / name
        worker_dir = root / "worker"
        for path in root.rglob("*.py"):
            if path == root / "module.py" or worker_dir in path.parents:
                continue
            for target in _import_targets(path):
                if target == f"modules.{name}.worker" or target.startswith(f"modules.{name}.worker."):
                    offenders.append((path.relative_to(SERVER).as_posix(), target))
    assert not offenders, f"只有 module.py 可以引用本模块的 worker/：{offenders}"
```

- [ ] **Step 2: 验证该用例能抓到违规**

临时新建 `server/modules/example_a/_probe.py`，内容 `from modules.example_a.worker import LOOPS`，运行：

Run: `pytest tests/platforms/test_architecture.py::test_only_module_py_imports_own_worker -q`
Expected: FAIL，报出 `modules/example_a/_probe.py`

然后删除 `server/modules/example_a/_probe.py`，再次运行，Expected: PASS

- [ ] **Step 3: 写示例循环的失败用例**

新建 `server/tests/modules/example_a/test_worker.py`：

```python
"""示例后台循环：先跑一轮再休眠，收到停机后退出。"""

import asyncio
import logging

import pytest

from modules.example_a import service
from modules.example_a.module import MODULE
from modules.example_a.worker import report_item_count
from platforms.contract import LoopContext

pytestmark = pytest.mark.db


def test_module_declares_report_loop():
    assert [loop.name for loop in MODULE.loops] == ["report_item_count"]


async def test_count_items(session):
    before = await service.count_items(session)
    await service.create_item(session, "计数")
    assert await service.count_items(session) == before + 1


async def test_report_item_count_runs_once_then_stops(db_ready, caplog):
    stopping = asyncio.Event()
    stopping.set()
    logger = logging.getLogger("worker.example_a.report_item_count")
    with caplog.at_level(logging.INFO, logger="worker.example_a.report_item_count"):
        await asyncio.wait_for(report_item_count(LoopContext("example_a", "report_item_count", stopping, logger)), 2)
    assert "当前条目数" in caplog.text
```

Run: `pytest tests/modules/example_a/test_worker.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'modules.example_a.worker'`

- [ ] **Step 4: 实现**

`server/modules/example_a/service.py`：import 改为

```python
from sqlalchemy import func, select
```

文件末尾追加：

```python


async def count_items(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Item))
```

新建 `server/modules/example_a/worker/__init__.py`：

```python
"""后台循环：只由 module.py 引用，经 python main.py worker example_a 运行。

import 时不得产生副作用（建连接、开线程、启动外部进程），API 进程也会导入本包。
"""

from modules.example_a import service
from platforms.contract import BackgroundLoop, LoopContext
from platforms.db import session_scope

REPORT_INTERVAL_SECONDS = 30


async def report_item_count(ctx: LoopContext) -> None:
    while True:
        async with session_scope() as session:
            count = await service.count_items(session)
        ctx.logger.info("当前条目数：%d", count)
        if not await ctx.sleep(REPORT_INTERVAL_SECONDS):
            return


LOOPS = (BackgroundLoop("report_item_count", report_item_count),)
```

`server/modules/example_a/module.py`：import 区加入 `from modules.example_a.worker import LOOPS`（放在 `from modules.example_a.api import router` 之后），`ModuleSpec(...)` 的 `menus=(...)` 之后追加 `loops=LOOPS,`。

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/modules/example_a tests/platforms/test_architecture.py -q`
Expected: PASS

- [ ] **Step 6: 端到端冒烟**

Run: `timeout -s TERM 5 python main.py worker example_a; echo "exit=$?"`
Expected: 日志依次出现 `模块已启动：example_a`、`worker 已启动：example_a.report_item_count`、`当前条目数：<n>`，5 秒后 `收到停机信号`、`worker 已停止`，`exit=0`

Run: `python main.py worker example_a --loops missing; echo "exit=$?"`
Expected: `worker 启动失败：模块 example_a 中不存在循环：['missing']，可用循环：['report_item_count']`，`exit=1`

Run: `python main.py worker example_b; echo "exit=$?"`
Expected: `worker 启动失败：模块 ['example_b'] 没有可运行的后台循环`，`exit=1`

- [ ] **Step 7: 全量回归、lint 并提交**

Run: `pytest -q && ruff check main.py platforms modules tests`
Expected: 全部通过

```bash
git add server/tests/platforms/test_architecture.py server/modules/example_a server/tests/modules/example_a/test_worker.py
git commit -m "feat(example_a): add sample worker loop and worker import boundary test"
```

---

### Task 8: compose 模板与架构规范

**Files:**
- Modify: `deploy/docker-compose.yml`
- Modify: `docs/架构规范.md`

**Interfaces:**
- Consumes: Task 1–7 的全部命名与命令

- [ ] **Step 1: compose 抽出共享环境变量**

`deploy/docker-compose.yml`：在 `name: lancha` 与 `services:` 之间插入：

```yaml

# server、migrate 与各 worker 共用：ENABLED_MODULES 不一致会出现「能建单但没人执行」的静默故障
x-backend-env: &backend-env
  POSTGRES_HOST: postgres
  POSTGRES_USER: ${POSTGRES_USER:-lancha}
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-lancha}
  POSTGRES_DB: ${POSTGRES_DB:-lancha_ai_studio}
  # 为空表示加载全部模块；按模块分批上线时在这里指定
  ENABLED_MODULES: ${ENABLED_MODULES:-}
```

`migrate` 的 `environment:` 整段替换为：

```yaml
    environment: *backend-env
```

`server` 的 `environment:` 整段替换为：

```yaml
    environment:
      <<: *backend-env
      APP_HOST: 0.0.0.0
      AUTH_MODE: ${AUTH_MODE:-feishu}
      FEISHU_APP_ID: ${FEISHU_APP_ID:-}
      FEISHU_APP_SECRET: ${FEISHU_APP_SECRET:-}
      FEISHU_REDIRECT_URI: ${FEISHU_REDIRECT_URI:-}
      COOKIE_SECURE: ${COOKIE_SECURE:-true}
      FRONTEND_BASE_URL: ${FRONTEND_BASE_URL:-http://localhost:8080}
```

在 `server` 服务之后、`web` 服务之前插入：

```yaml
  # 有后台循环的模块各自一个 worker 服务，复制下面的模板并替换 <模块名>：
  # worker-<模块名>:
  #   build: *server-build              # 需要系统依赖的模块改用 modules/<模块名>/worker.Dockerfile
  #   command: ["python", "main.py", "worker", "<模块名>"]
  #   restart: unless-stopped
  #   stop_grace_period: 60s            # 大于该模块循环的最大 stop_timeout
  #   environment:
  #     <<: *backend-env
  #     POSTGRES_POOL_SIZE: 3           # 每个持锁的单例循环额外占用一个连接
  #   depends_on:
  #     postgres:
  #       condition: service_healthy
  #     migrate:
  #       condition: service_completed_successfully
```

- [ ] **Step 2: 校验 compose**

Run: `cd ../deploy && docker compose -p lancha config --quiet && docker compose -p lancha config | grep -A12 "^  server:" | grep -E "POSTGRES_HOST|ENABLED_MODULES|AUTH_MODE"; cd ../server`
Expected: 无报错；输出包含 `POSTGRES_HOST: postgres`、`ENABLED_MODULES`、`AUTH_MODE`

- [ ] **Step 3: 更新架构规范**

`docs/架构规范.md`：

1. 开头第二段「一个后端进程按模块装载」改为「后端按模块装载，API 进程与各模块的 worker 进程共用同一套装载流程」。

2. §1 目录树中 `│  │  ├─ events.py          进程内事件总线` 之后插入：

```
│  │  ├─ lifecycle.py       模块生命周期：事件订阅、启动与关闭钩子（API 与 worker 共用）
```

`│  │  └─ registry.py        已加载模块的注册表` 改为：

```
│  │  ├─ registry.py        已加载模块的注册表
│  │  └─ worker/            worker 进程骨架：循环托管、看门狗、单例锁
```

3. §2 命名表在「迁移分支」行之后追加：

```
| 后台循环 | `<模块名>.<循环名>`，循环名规则同模块名 | `example_a.report_item_count` |
| worker 服务 | `worker-<模块名>` | `worker-example_a` |
| 循环日志 | `worker.<模块名>.<循环名>` | `worker.example_a.report_item_count` |
```

表下一句「违反前四项的…」改为「违反前四项及循环名规则的，`platforms/gateway/loader.py` 在进程启动时直接拒绝加载。」

4. §3「**这些约束是可执行的，不是口头约定**」之前插入：

````markdown
**后台逻辑放在 worker 进程**

模块在 `worker/` 中实现后台循环，经 `module.py` 的 `ModuleSpec.loops` 声明，由 `python main.py worker <模块名>` 托管运行。平台只负责托管：异常退避重启、优雅停机、事件循环看门狗、单例锁；任务表、租约、幂等、重试由模块自己实现。

- 除 `module.py` 外，模块内任何代码不得 import 自己的 `worker/`（架构测试检查）；`worker/` 在 import 时不得建连接、开线程或启动外部进程。
- `on_startup` / `on_shutdown` 会在 API 进程和每个装载该模块的 worker 进程中各执行一次，必须幂等，且不得启动后台任务。
- 事件只在进程内派发。worker 只装载目标模块及其 `depends_on`，它发布的事件其他模块收不到；执行只由本模块 schema 中的状态驱动，需要通知其他模块时写自己的状态表，由对方经 `contract.py` 查询。
- 不能重复执行的循环声明 `singleton=True`（PostgreSQL advisory lock，失锁即停，尽力而为）；其余循环在多副本下的并发安全由模块保证，如 `FOR UPDATE SKIP LOCKED`。
- CPU 密集操作放到线程池或子进程，事件循环阻塞超过 `WORKER_WATCHDOG_TIMEOUT`（默认 60 秒）进程会被看门狗终止。
- worker 尽量少同步调用其他模块的 `contract.py`：拆分模块时这些调用要改成远程调用。

```python
async def report_item_count(ctx: LoopContext) -> None:
    while True:
        async with session_scope() as session:
            ...
        if not await ctx.sleep(30):      # 收到停机信号返回 False
            return

LOOPS = (BackgroundLoop("report_item_count", report_item_count),)
```

````

5. §6 代码块中 `5. 复制 server/tests/modules/example 为 server/tests/modules/<模块名>` 之后插入：

```
6. 有后台逻辑时在 worker/__init__.py 声明 LOOPS，module.py 传入 loops=LOOPS
```

并把其后的编号依次顺延（前端 7、8，验证 9、10）。

6. §7 代码块中 `python main.py` 之后插入：

```
python main.py worker <模块名>        # 另开终端运行该模块的后台循环
```

7. §8 在「同一个镜像通过 `ENABLED_MODULES`…」之后追加：

```markdown
有后台循环的模块按 compose 中的模板各加一个 `worker-<模块名>` 服务，与 `server` 共用 `x-backend-env`，保证 `ENABLED_MODULES` 一致。worker 只装载目标模块，模块不在 `ENABLED_MODULES` 中时拒绝启动。轻量模块可以合并为 `python main.py worker a,b`；模块内的重循环可以用 `--loops` 拆到单独的服务。需要系统依赖（浏览器、ffmpeg 等）的模块提供自己的 `worker.Dockerfile`，不进 API 镜像。
```

8. §9 第一行「多租户、数据权限、微服务拆分、前端运行时微前端、后台任务队列、模块脚手架命令。」之后追加一行：

```
后台循环托管已支持（见第 3 节），但通用任务队列、cron 调度、跨进程事件仍不做，需要时由模块在自己的 schema 内实现。
```

- [ ] **Step 4: 最终验证**

Run: `pytest -q && ruff check main.py platforms modules tests && python -m alembic -n platform check && python -m alembic -n example_a check`
Expected: 全部通过；alembic 两个分支均输出 `No new upgrade operations detected.`

- [ ] **Step 5: 提交**

```bash
git add deploy/docker-compose.yml docs/架构规范.md
git commit -m "docs: document worker processes in architecture spec and compose template"
```
