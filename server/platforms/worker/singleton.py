"""单例循环：用 PostgreSQL 会话级 advisory lock 保证同名循环全局只运行一份。

锁绑定在一条独占连接上，连接断开即释放。持锁期间定期在该连接上探活，探活失败视为失锁，
立即取消循环，避免与接管的副本同时运行。连接静默断开到服务端释放锁之间仍有短暂窗口，
绝对不能重复的业务操作仍需模块自己保证幂等。不支持事务级连接池（如 PgBouncer transaction 模式）。
"""

import asyncio

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
                    await _release(conn, key, check_interval)
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
                await asyncio.wait_for(conn.execute(_PING), check_interval)
            except Exception as exc:
                raise SingletonLockLost(f"单例锁连接失效：{ctx.module}.{ctx.name}") from exc
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def _release(conn: AsyncConnection, key: str, timeout: float) -> None:
    """释放失败或超时时作废连接：会话级锁随连接关闭而释放，避免带锁的连接回到连接池。"""
    try:
        await asyncio.wait_for(conn.execute(_UNLOCK, {"key": key}), timeout)
    except asyncio.CancelledError:
        await conn.invalidate()
        raise
    except Exception:  # noqa: BLE001
        await conn.invalidate()
