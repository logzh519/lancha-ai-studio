"""后台循环：只由 module.py 引用，经 python main.py worker tiktok_studio 运行。

import 时不得产生副作用（建连接、开线程、启动外部进程），API 进程也会导入本包。

自动导入的商品分两个阶段补全：product_crawl 抓 Amazon 详情与主副图，product_view 从中识别三视图参考图。
两个循环都是单例，状态只记在 product_master 上，启动时把上次中断留下的 running 退回 pending。
"""

import asyncio
from collections.abc import Awaitable, Callable

from modules.tiktok_studio import service, tools
from platforms.contract import BackgroundLoop, LoopContext
from platforms.db import session_scope
from platforms.llm import AsyncLLMClient
from platforms.storage import get_storage

IDLE_SECONDS = 5
CRAWL_CONCURRENCY = 3
VIEW_CONCURRENCY = 2
CRAWL_TIMEOUT = 30.0
VIEW_TIMEOUT = 120.0
VIEW_LLM_PROVIDER = "lch_tk"


async def _run_job(
    ctx: LoopContext,
    product_id: int,
    run: Callable[[], Awaitable[tools.ToolResult]],
    complete: Callable,
    fail: Callable,
) -> None:
    """子任务自行吞掉业务异常并记为失败，避免一个商品出错连带取消整批。"""
    try:
        result = await run()
    except Exception as exc:
        ctx.logger.exception("商品 %d 处理异常", product_id)
        result = tools.ToolResult(False, {}, "unexpected_error", f"{type(exc).__name__}: {exc}")
    async with session_scope() as session:
        if result.success:
            await complete(session, product_id, result.output)
        else:
            await fail(session, product_id, result.error_message or result.error_code or "未知错误")


async def _run_batches(ctx: LoopContext, claim: Callable, handle: Callable) -> None:
    while not ctx.stopping.is_set():
        async with session_scope() as session:
            jobs = await claim(session)
        if not jobs:
            if not await ctx.sleep(IDLE_SECONDS):
                return
            continue
        async with asyncio.TaskGroup() as group:
            for job in jobs:
                group.create_task(handle(job))


async def product_crawl(ctx: LoopContext) -> None:
    async with session_scope() as session:
        await service.reset_running_crawls(session)
    crawler = tools.build("amazon_crawler", tools.ToolDeps(session=None, storage=get_storage()))

    async def handle(job: service.CrawlJob) -> None:
        settings = tools.ToolSettings(timeout=CRAWL_TIMEOUT, trace_id=f"product_crawl:{job.product_id}")
        await _run_job(
            ctx, job.product_id,
            lambda: crawler.execute({"asin": job.asin}, settings),
            service.complete_crawl, service.fail_crawl,
        )

    await _run_batches(ctx, lambda session: service.claim_crawl_jobs(session, CRAWL_CONCURRENCY), handle)


async def product_view(ctx: LoopContext) -> None:
    async with session_scope() as session:
        await service.reset_running_views(session)
    llm = AsyncLLMClient(provider=VIEW_LLM_PROVIDER)
    selector = tools.build("view_select", tools.ToolDeps(session=None, llm=llm))

    async def handle(job: service.ViewJob) -> None:
        if len(job.images) < 2:
            async with session_scope() as session:
                await service.fail_view(session, job.product_id, f"可用于识别的商品图只有 {len(job.images)} 张，至少需要 2 张")
            return
        settings = tools.ToolSettings(timeout=VIEW_TIMEOUT, trace_id=f"product_view:{job.product_id}")
        payload = {"images": job.images, "bullet_points": job.bullet_points, "description": job.description}
        await _run_job(
            ctx, job.product_id,
            lambda: selector.execute(payload, settings),
            service.complete_view, service.fail_view,
        )

    try:
        await _run_batches(ctx, lambda session: service.claim_view_jobs(session, VIEW_CONCURRENCY), handle)
    finally:
        await llm.aclose()


LOOPS = (
    BackgroundLoop("product_crawl", product_crawl, singleton=True),
    BackgroundLoop("product_view", product_view, singleton=True),
)
