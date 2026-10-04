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
