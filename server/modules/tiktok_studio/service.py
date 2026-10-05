"""业务逻辑层：事务边界在调用方（get_session 依赖），这里只管业务。"""

from dataclasses import dataclass

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok_studio.models import SCHEMA, ProductMaster, ScriptTemplate
from modules.tiktok_studio.schemas import ProductMasterFields, ScriptTemplateFields

ERROR_MAX_LENGTH = 2000


def _like_pattern(keyword: str) -> str:
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def list_script_templates(
    session: AsyncSession, offset: int, limit: int, keyword: str | None = None
) -> tuple[list[ScriptTemplate], int]:
    conditions = []
    if keyword:
        conditions.append(ScriptTemplate.name.ilike(_like_pattern(keyword), escape="\\"))
    total = await session.scalar(select(func.count()).select_from(ScriptTemplate).where(*conditions))
    stmt = select(ScriptTemplate).where(*conditions).order_by(ScriptTemplate.id.desc()).offset(offset).limit(limit)
    return list((await session.execute(stmt)).scalars()), total


async def get_script_template(session: AsyncSession, template_id: int) -> ScriptTemplate | None:
    return await session.get(ScriptTemplate, template_id)


async def create_script_template(
    session: AsyncSession, fields: ScriptTemplateFields, created_by: int | None, template_id: int | None = None
) -> ScriptTemplate:
    template = ScriptTemplate(id=template_id, created_by=created_by, **fields.model_dump())
    session.add(template)
    await session.flush()
    if template_id is not None:
        await _sync_id_sequence(session)
    await session.refresh(template)
    return template


async def update_script_template(
    session: AsyncSession, template: ScriptTemplate, fields: ScriptTemplateFields
) -> ScriptTemplate:
    for key, value in fields.model_dump().items():
        setattr(template, key, value)
    await session.flush()
    await session.refresh(template)
    return template


async def delete_script_template(session: AsyncSession, template: ScriptTemplate) -> None:
    await session.delete(template)
    await session.flush()


async def pick_script_template(session: AsyncSession, category: str) -> ScriptTemplate | None:
    """从正式模板里随机取一条；候选池 = 全品类模板 + 指定类目的模板。"""
    stmt = (
        select(ScriptTemplate)
        .where(ScriptTemplate.status == "formal", ScriptTemplate.category.in_(("all", category)))
        .order_by(func.random())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def list_product_masters(
    session: AsyncSession, offset: int, limit: int, keyword: str | None = None
) -> tuple[list[ProductMaster], int]:
    conditions = []
    if keyword:
        pattern = _like_pattern(keyword)
        columns = (ProductMaster.sku, ProductMaster.asin, ProductMaster.pid)
        conditions.append(or_(*(column.ilike(pattern, escape="\\") for column in columns)))
    total = await session.scalar(select(func.count()).select_from(ProductMaster).where(*conditions))
    stmt = select(ProductMaster).where(*conditions).order_by(ProductMaster.id.desc()).offset(offset).limit(limit)
    return list((await session.execute(stmt)).scalars()), total


async def get_product_master(session: AsyncSession, product_id: int) -> ProductMaster | None:
    return await session.get(ProductMaster, product_id)


async def create_product_master(
    session: AsyncSession, fields: ProductMasterFields, created_by: int | None
) -> ProductMaster:
    product = ProductMaster(created_by=created_by, **fields.model_dump())
    session.add(product)
    await session.flush()
    await session.refresh(product)
    return product


async def update_product_master(
    session: AsyncSession, product: ProductMaster, fields: ProductMasterFields
) -> ProductMaster:
    for key, value in fields.model_dump().items():
        setattr(product, key, value)
    await session.flush()
    await session.refresh(product)
    return product


async def delete_product_master(session: AsyncSession, product: ProductMaster) -> None:
    await session.delete(product)
    await session.flush()


async def existing_product_keys(session: AsyncSession, skus: list[str]) -> set[tuple[str, str | None]]:
    """已入库商品的（大写货号, ASIN），自动导入据此跳过重复记录。"""
    stmt = select(func.upper(ProductMaster.sku), ProductMaster.asin).where(func.upper(ProductMaster.sku).in_(skus))
    return {(sku, asin) for sku, asin in await session.execute(stmt)}


async def create_imported_products(
    session: AsyncSession, records: list[dict], created_by: int | None
) -> list[ProductMaster]:
    """按 product_lookup 的 SKU 记录建商品，两个后台阶段都置为 pending 等 worker 处理。"""
    products = [
        ProductMaster(
            sku=record["sku"],
            asin=record["asin"],
            color=record["color"],
            store=record["store"],
            pid=record["pid"],
            category=record["category"],
            crawl_status="pending",
            view_status="pending",
            created_by=created_by,
        )
        for record in records
    ]
    session.add_all(products)
    await session.flush()
    for product in products:
        await session.refresh(product)
    return products


async def retry_product_import(session: AsyncSession, product: ProductMaster) -> bool:
    """把失败的阶段重置为 pending；抓取失败时三视图也要重做。没有失败阶段返回 False。"""
    if product.crawl_status == "failed":
        product.crawl_status, product.crawl_error = "pending", None
        product.view_status, product.view_error = "pending", None
    elif product.view_status == "failed":
        product.view_status, product.view_error = "pending", None
    else:
        return False
    await session.flush()
    await session.refresh(product)
    return True


@dataclass(frozen=True)
class CrawlJob:
    product_id: int
    asin: str | None


@dataclass(frozen=True)
class ViewJob:
    product_id: int
    images: list[str]
    bullet_points: list[str]
    description: str | None


async def reset_running_crawls(session: AsyncSession) -> None:
    """抓取循环是单例，启动时残留的 running 只可能来自上次中断，退回 pending 重做。"""
    stmt = update(ProductMaster).where(ProductMaster.crawl_status == "running").values(crawl_status="pending")
    await session.execute(stmt)


async def reset_running_views(session: AsyncSession) -> None:
    stmt = update(ProductMaster).where(ProductMaster.view_status == "running").values(view_status="pending")
    await session.execute(stmt)


async def claim_crawl_jobs(session: AsyncSession, limit: int) -> list[CrawlJob]:
    stmt = (
        select(ProductMaster)
        .where(ProductMaster.crawl_status == "pending")
        .order_by(ProductMaster.id)
        .limit(limit)
    )
    products = list((await session.execute(stmt)).scalars())
    for product in products:
        product.crawl_status = "running"
    await session.flush()
    return [CrawlJob(product.id, product.asin) for product in products]


async def claim_view_jobs(session: AsyncSession, limit: int) -> list[ViewJob]:
    """三视图识别依赖抓取得到的主图副图，只领取抓取已完成的商品。"""
    stmt = (
        select(ProductMaster)
        .where(ProductMaster.view_status == "pending", ProductMaster.crawl_status == "done")
        .order_by(ProductMaster.id)
        .limit(limit)
    )
    products = list((await session.execute(stmt)).scalars())
    for product in products:
        product.view_status = "running"
    await session.flush()
    return [
        ViewJob(
            product.id,
            [url for url in (product.main_image_url, *product.sub_images) if url],
            (product.selling_points or "").splitlines(),
            product.description,
        )
        for product in products
    ]


async def complete_crawl(session: AsyncSession, product_id: int, output: dict) -> None:
    """output 为 amazon_crawler 的输出；商品已被删除时忽略。"""
    product = await session.get(ProductMaster, product_id)
    if product is None:
        return
    main_image = output["main_image"] or {}
    product.description = output["description"]
    product.selling_points = "\n".join(output["bullet_points"]) or None
    product.main_image_url = main_image.get("url")
    product.sub_images = [image["url"] for image in output["gallery_images"] if image["url"]]
    product.crawl_status, product.crawl_error = "done", None
    await session.flush()


async def complete_view(session: AsyncSession, product_id: int, output: dict) -> None:
    """output 为 view_select 的输出，按正面、侧面、背面的顺序写入三视图参考图；侧面可能缺失。"""
    product = await session.get(ProductMaster, product_id)
    if product is None:
        return
    views = (output["front_url"], output["side_url"], output["back_url"])
    product.three_view_reference_images = [url for url in views if url]
    product.view_status, product.view_error = "done", None
    await session.flush()


async def fail_crawl(session: AsyncSession, product_id: int, message: str) -> None:
    product = await session.get(ProductMaster, product_id)
    if product is None:
        return
    product.crawl_status, product.crawl_error = "failed", message[:ERROR_MAX_LENGTH]
    await session.flush()


async def fail_view(session: AsyncSession, product_id: int, message: str) -> None:
    product = await session.get(ProductMaster, product_id)
    if product is None:
        return
    product.view_status, product.view_error = "failed", message[:ERROR_MAX_LENGTH]
    await session.flush()


async def _sync_id_sequence(session: AsyncSession) -> None:
    """指定主键插入不会推进自增序列，插入后把序列对齐到当前最大 ID，避免后续新建撞主键。"""
    table = f"{SCHEMA}.{ScriptTemplate.__tablename__}"
    await session.execute(
        text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")
    )
