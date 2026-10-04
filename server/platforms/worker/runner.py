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
