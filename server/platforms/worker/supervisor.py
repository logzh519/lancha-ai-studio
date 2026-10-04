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
