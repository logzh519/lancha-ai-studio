"""后台循环托管：异常退避重启、正常返回即结束、停机可打断等待。"""

import asyncio
import logging

from platforms.contract import LoopContext
from platforms.worker.supervisor import supervise


def _ctx(stopping: asyncio.Event | None = None) -> LoopContext:
    return LoopContext("demo", "job", stopping or asyncio.Event(), logging.getLogger("worker.demo.job"))


async def test_sleep_returns_true_after_timeout():
    assert await _ctx().sleep(0.01) is True


async def test_sleep_returns_false_when_stopping():
    stopping = asyncio.Event()
    asyncio.get_running_loop().call_later(0.01, stopping.set)
    assert await _ctx(stopping).sleep(5) is False


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
