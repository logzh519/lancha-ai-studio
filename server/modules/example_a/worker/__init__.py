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
