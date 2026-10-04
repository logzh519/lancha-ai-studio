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


async def test_run_failure_releases_lock(db_ready):
    ran = []

    async def failing(ctx):
        raise RuntimeError("boom")

    async def body(ctx):
        ran.append(ctx.name)

    with pytest.raises(RuntimeError):
        await run_exclusive(_ctx(asyncio.Event(), "run_failure"), failing, **FAST)

    await asyncio.wait_for(run_exclusive(_ctx(asyncio.Event(), "run_failure"), body, **FAST), 1)
    assert ran == ["run_failure"]


async def test_ping_timeout_counts_as_lock_loss(db_ready, monkeypatch):
    cancelled = asyncio.Event()
    ran = []

    async def hanging(ctx):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def body(ctx):
        ran.append(ctx.name)

    monkeypatch.setattr("platforms.worker.singleton._PING", text("SELECT pg_sleep(1)"))
    with pytest.raises(SingletonLockLost):
        await asyncio.wait_for(run_exclusive(_ctx(asyncio.Event(), "ping_timeout"), hanging, **FAST), 2)
    assert cancelled.is_set()

    monkeypatch.undo()
    await asyncio.wait_for(run_exclusive(_ctx(asyncio.Event(), "ping_timeout"), body, **FAST), 1)
    assert ran == ["ping_timeout"]


async def test_unlock_failure_invalidates_connection(db_ready, monkeypatch):
    ran = []

    async def body(ctx):
        ran.append(ctx.name)

    monkeypatch.setattr("platforms.worker.singleton._UNLOCK", text("SELECT 1/0"))
    await asyncio.wait_for(run_exclusive(_ctx(asyncio.Event(), "unlock_failure"), body, **FAST), 1)
    monkeypatch.undo()

    async with session_scope() as session:
        held = await session.scalar(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted "
                "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
                "AND objid = (hashtextextended('worker_test.unlock_failure', 0) & 4294967295)::oid"
            )
        )
    assert held == 0

    await asyncio.wait_for(run_exclusive(_ctx(asyncio.Event(), "unlock_failure"), body, **FAST), 1)
    assert ran == ["unlock_failure", "unlock_failure"]
