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
