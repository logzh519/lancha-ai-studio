"""后台循环：只由 module.py 引用，经 python main.py worker tiktok_studio 运行。

import 时不得产生副作用（建连接、开线程、启动外部进程），API 进程也会导入本包。

自动导入的商品分三个阶段补全：product_crawl 抓 Amazon 详情与主副图，product_view 从中识别三视图参考图，
product_three_view 用参考图生成三视图。三个循环都是单例，状态只记在 product_master 上，启动时把上次中断留下的
running 退回 pending。
"""

import asyncio
from collections.abc import Awaitable, Callable

from modules.tiktok_studio import service, tools
from platforms.contract import BackgroundLoop, LoopContext
from platforms.db import session_scope
from platforms.llm import AsyncLLMClient
from platforms.storage import get_storage

IDLE_SECONDS = 5               # 没有待处理商品时，等待多少秒再查询下一轮
CRAWL_CONCURRENCY = 3          # 抓取每轮领取的商品数，同批并发执行，整批结束才领下一批
VIEW_CONCURRENCY = 2           # 视角识别每轮领取的商品数，含义同上；调用视觉模型，比抓取更慢更贵
CRAWL_TIMEOUT = 30.0           # 抓取时单次 HTTP 请求的超时秒数，不是整个商品的总时长
VIEW_TIMEOUT = 120.0           # 视角识别时单次图片下载或模型调用的超时秒数
VIEW_LLM_PROVIDER = "lch_tk"   # 视角识别所用的 LLM 供应商，见 platforms.llm.client._resolve_config
GEN_CONCURRENCY = 2            # 三视图生成每轮领取的商品数；每个商品调用一次生图模型，最慢最贵
GEN_TIMEOUT = 300.0            # 三视图生成时单次图片下载、视觉识别或生图调用的超时秒数
GEN_LLM_PROVIDER = "lch_tk"    # 三视图生成所用的 LLM 供应商，视觉识别用其默认模型，生图模型由 Tool 指定


async def _run_job(
    ctx: LoopContext,
    product_id: int,
    payload: dict,
    run: Callable[[dict], Awaitable[tools.ToolResult]],
    complete: Callable,
    fail: Callable,
) -> None:
    """子任务自行吞掉业务异常并记为失败，避免一个商品出错连带取消整批。

    失败时连同 payload 与 Tool 输出一起记下；complete 返回不再被引用的存储对象，事务提交后再删除。
    """
    try:
        result = await run(payload)
    except Exception as exc:
        ctx.logger.exception("商品 %d 处理异常", product_id)
        result = tools.ToolResult(False, {}, "unexpected_error", f"{type(exc).__name__}: {exc}")
    orphans: list[service.StoredRef] = []
    async with session_scope() as session:
        if result.success:
            orphans = await complete(session, product_id, result.output)
        else:
            await fail(session, product_id, service.StageFailure(
                result.error_message or result.error_code or "未知错误", payload, result.output, result.error_code,
            ))
    await service.purge_objects(orphans)


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
            ctx, job.product_id, {"asin": job.asin},
            lambda payload: crawler.execute(payload, settings),
            service.complete_crawl, service.fail_crawl,
        )

    await _run_batches(ctx, lambda session: service.claim_crawl_jobs(session, CRAWL_CONCURRENCY), handle)


async def product_view(ctx: LoopContext) -> None:
    async with session_scope() as session:
        await service.reset_running_views(session)
    llm = AsyncLLMClient(provider=VIEW_LLM_PROVIDER)
    selector = tools.build("view_select", tools.ToolDeps(session=None, llm=llm))

    async def handle(job: service.ViewJob) -> None:
        payload = {"images": job.images, "bullet_points": job.bullet_points, "description": job.description}
        if len(job.images) < 2:
            async with session_scope() as session:
                await service.fail_view(session, job.product_id, service.StageFailure(
                    f"可用于识别的商品图只有 {len(job.images)} 张，至少需要 2 张", payload,
                ))
            return
        settings = tools.ToolSettings(timeout=VIEW_TIMEOUT, trace_id=f"product_view:{job.product_id}")
        await _run_job(
            ctx, job.product_id, payload,
            lambda payload: selector.execute(payload, settings),
            service.complete_view, service.fail_view,
        )

    try:
        await _run_batches(ctx, lambda session: service.claim_view_jobs(session, VIEW_CONCURRENCY), handle)
    finally:
        await llm.aclose()


def _gen_payload(job: service.GenJob) -> dict:
    """参考图按正面、侧面、背面存储；无侧面时只有正面、背面两张。"""
    front, *rest = job.reference_images
    side, back = (rest[0], rest[1]) if job.side_kind != "none" else (None, rest[0])
    return {
        "asin": job.asin,
        "product_code": job.sku,
        "color": job.color or "",
        "bullet_points": job.bullet_points,
        "description": job.description,
        "front_url": front,
        "back_url": back,
        "side_url": side,
        "side_kind": job.side_kind,
    }


async def product_three_view(ctx: LoopContext) -> None:
    async with session_scope() as session:
        await service.reset_running_gens(session)
    llm = AsyncLLMClient(provider=GEN_LLM_PROVIDER)
    generator = tools.build("three_view_gen", tools.ToolDeps(session=None, storage=get_storage(), llm=llm))

    async def handle(job: service.GenJob) -> None:
        expected = 3 if job.side_kind != "none" else 2
        if len(job.reference_images) != expected:
            async with session_scope() as session:
                await service.fail_gen(session, job.product_id, service.StageFailure(
                    f"参考图数量 {len(job.reference_images)} 与侧面类型 {job.side_kind} 不符，请重新识别参考图",
                    {"reference_images": job.reference_images, "side_kind": job.side_kind},
                ))
            return
        settings = tools.ToolSettings(timeout=GEN_TIMEOUT, trace_id=f"product_three_view:{job.product_id}")
        await _run_job(
            ctx, job.product_id, _gen_payload(job),
            lambda payload: generator.execute(payload, settings),
            service.complete_gen, service.fail_gen,
        )

    try:
        await _run_batches(ctx, lambda session: service.claim_gen_jobs(session, GEN_CONCURRENCY), handle)
    finally:
        await llm.aclose()


LOOPS = (
    BackgroundLoop("product_crawl", product_crawl, singleton=True),
    BackgroundLoop("product_view", product_view, singleton=True),
    BackgroundLoop("product_three_view", product_three_view, singleton=True),
)
