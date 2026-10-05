"""业务逻辑层：事务边界在调用方（get_session 依赖），这里只管业务。

商品图片引用对象存储里的对象，每个商品（ASIN）独占一套资源。改动图片字段的函数返回该商品不再引用的对象，
调用方提交事务后再用 purge_objects 删除，避免事务回滚时对象已被删掉。
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok_studio.models import SCHEMA, ProductMaster, ScriptTemplate
from modules.tiktok_studio.schemas import (
    EXTERNAL,
    ProductMasterFields,
    ScriptTemplateFields,
)
from platforms.storage import get_storage

ERROR_MAX_LENGTH = 2000
logger = logging.getLogger(__name__)


@dataclass(frozen=True, order=True)
class StoredRef:
    """对象存储中的一个对象。"""

    type: str
    key: str


class UnknownStoredObject(ValueError):
    """客户端提交了商品原本没有的存储对象；只允许保留或移除已有对象、新增外部链接。"""


def _stored_refs(images: list[dict | None]) -> set[StoredRef]:
    return {
        StoredRef(image["type"], image["key"])
        for image in images
        if image and image.get("type") != EXTERNAL and image.get("key")
    }


def _product_refs(product: ProductMaster) -> set[StoredRef]:
    return _stored_refs([
        product.main_image, *product.sub_images, *product.three_view_images, *product.three_view_reference_images,
    ])


def _fields_refs(fields: ProductMasterFields) -> set[StoredRef]:
    images = [fields.main_image, *fields.sub_images, *fields.three_view_images, *fields.three_view_reference_images]
    return _stored_refs([image.model_dump() if image else None for image in images])


async def purge_objects(refs: list[StoredRef]) -> None:
    """删除存储对象，须在事务提交后调用。删除失败只记日志：残留对象不影响业务数据。"""
    for ref in refs:
        try:
            await asyncio.to_thread(get_storage(ref.type).delete_file, ref.key)
        except Exception:
            logger.exception("删除存储对象失败 %s:%s", ref.type, ref.key)


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


def _check_known_objects(fields: ProductMasterFields, known: set[StoredRef]) -> None:
    unknown = _fields_refs(fields) - known
    if unknown:
        raise UnknownStoredObject(f"不能引用商品原本没有的存储对象：{', '.join(r.key for r in sorted(unknown))}")


async def create_product_master(
    session: AsyncSession, fields: ProductMasterFields, created_by: int | None
) -> ProductMaster:
    _check_known_objects(fields, set())
    product = ProductMaster(created_by=created_by, **fields.model_dump())
    session.add(product)
    await session.flush()
    await session.refresh(product)
    return product


async def update_product_master(
    session: AsyncSession, product: ProductMaster, fields: ProductMasterFields
) -> tuple[ProductMaster, list[StoredRef]]:
    """返回更新后的商品与需要删除的存储对象。"""
    before = _product_refs(product)
    _check_known_objects(fields, before)
    for key, value in fields.model_dump().items():
        setattr(product, key, value)
    await session.flush()
    await session.refresh(product)
    return product, sorted(before - _product_refs(product))


IMAGE_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
UPLOAD_PREFIX = "tiktok_studio/product_masters"


async def upload_product_image(
    session: AsyncSession, product: ProductMaster, field: str, content: bytes, mime: str
) -> tuple[dict, list[StoredRef]]:
    """上传图片并写入商品字段：主图与三视图（只有一张）直接替换，副图追加到末尾。返回新图片与需要删除的存储对象。"""
    storage = get_storage()
    key = f"{UPLOAD_PREFIX}/{product.id}/{uuid.uuid4().hex}.{IMAGE_EXTENSIONS[mime]}"
    record = await asyncio.to_thread(storage.upload, key, content)
    image = {"key": key, "url": record.url, "type": storage.type}

    def apply(target: ProductMaster) -> None:
        if field == "main_image":
            target.main_image = image
        elif field == "three_view_images":
            target.three_view_images = [image]
        else:
            setattr(target, field, [*getattr(target, field), image])

    orphans = await _apply_images(session, product, [image], apply)
    await session.refresh(product)
    return image, orphans


async def delete_product_master(session: AsyncSession, product: ProductMaster) -> list[StoredRef]:
    """返回需要删除的存储对象。"""
    refs = _product_refs(product)
    await session.delete(product)
    await session.flush()
    return sorted(refs)


async def existing_product_keys(session: AsyncSession, skus: list[str]) -> set[tuple[str, str | None]]:
    """已入库商品的（大写货号, ASIN），自动导入据此跳过重复记录。"""
    stmt = select(func.upper(ProductMaster.sku), ProductMaster.asin).where(func.upper(ProductMaster.sku).in_(skus))
    return {(sku, asin) for sku, asin in await session.execute(stmt)}


async def create_imported_products(
    session: AsyncSession, records: list[dict], created_by: int | None
) -> list[ProductMaster]:
    """按 product_lookup 的 SKU 记录建商品，三个后台阶段都置为 pending 等 worker 处理。"""
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
            gen_status="pending",
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
    """把失败的阶段及其下游阶段重置为 pending。没有失败阶段返回 False。"""
    if product.crawl_status == "failed":
        product.crawl_status, product.crawl_error = "pending", None
        product.view_status, product.view_error = "pending", None
        product.gen_status, product.gen_error = "pending", None
    elif product.view_status == "failed":
        product.view_status, product.view_error = "pending", None
        product.gen_status, product.gen_error = "pending", None
    elif product.gen_status == "failed":
        product.gen_status, product.gen_error = "pending", None
    else:
        return False
    await session.flush()
    await session.refresh(product)
    return True


class RegenerateUnavailable(ValueError):
    """当前状态不能重新生成三视图。"""


async def regenerate_three_view(session: AsyncSession, product: ProductMaster) -> None:
    """把三视图生成阶段置为 pending，由 worker 按当前参考图重新生成。"""
    if product.gen_status in ("pending", "running"):
        raise RegenerateUnavailable("三视图正在生成中，请稍后再试")
    if product.view_status != "done":
        raise RegenerateUnavailable("三视图参考图尚未识别完成，无法生成三视图")
    product.gen_status, product.gen_error = "pending", None
    _set_trace(product, "gen", None)
    await session.flush()
    await session.refresh(product)


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


@dataclass(frozen=True)
class GenJob:
    product_id: int
    asin: str | None
    sku: str
    color: str | None
    reference_images: list[str]     # 正面、侧面（可能缺失）、背面
    side_kind: str
    bullet_points: list[str]
    description: str | None


async def reset_running_crawls(session: AsyncSession) -> None:
    """抓取循环是单例，启动时残留的 running 只可能来自上次中断，退回 pending 重做。"""
    stmt = update(ProductMaster).where(ProductMaster.crawl_status == "running").values(crawl_status="pending")
    await session.execute(stmt)


async def reset_running_views(session: AsyncSession) -> None:
    stmt = update(ProductMaster).where(ProductMaster.view_status == "running").values(view_status="pending")
    await session.execute(stmt)


async def reset_running_gens(session: AsyncSession) -> None:
    stmt = update(ProductMaster).where(ProductMaster.gen_status == "running").values(gen_status="pending")
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
            [image["url"] for image in (product.main_image, *product.sub_images) if image and image.get("url")],
            (product.selling_points or "").splitlines(),
            product.description,
        )
        for product in products
    ]


async def claim_gen_jobs(session: AsyncSession, limit: int) -> list[GenJob]:
    """三视图生成依赖识别出的参考图，只领取参考图已完成的商品。"""
    stmt = (
        select(ProductMaster)
        .where(ProductMaster.gen_status == "pending", ProductMaster.view_status == "done")
        .order_by(ProductMaster.id)
        .limit(limit)
    )
    products = list((await session.execute(stmt)).scalars())
    for product in products:
        product.gen_status = "running"
    await session.flush()
    return [
        GenJob(
            product.id,
            product.asin,
            product.sku,
            product.color,
            [image["url"] for image in product.three_view_reference_images if image.get("url")],
            product.three_view_side_kind or "none",
            (product.selling_points or "").splitlines(),
            product.description,
        )
        for product in products
    ]


def _set_trace(product: ProductMaster, stage: str, trace: dict | None) -> None:
    """JSONB 字段原地修改不会被 ORM 感知，整体替换。"""
    traces = {key: value for key, value in product.import_trace.items() if key != stage}
    if trace is not None:
        traces[stage] = trace
    product.import_trace = traces


def _stored_object(image: dict) -> dict:
    return {"key": image["key"], "url": image["url"], "type": image["type"]}


async def _apply_images(session: AsyncSession, product: ProductMaster | None, uploaded: list[dict], apply) -> list[StoredRef]:
    """写入新图片并返回需要删除的对象；商品已被删除时，本次新上传的对象也无人引用。"""
    if product is None:
        return sorted(_stored_refs(uploaded))
    before = _product_refs(product)
    apply(product)
    await session.flush()
    return sorted(before - _product_refs(product))


async def complete_crawl(session: AsyncSession, product_id: int, output: dict) -> list[StoredRef]:
    """output 为 amazon_crawler 的输出。"""
    main_image = _stored_object(output["main_image"]) if output["main_image"] else None
    sub_images = [_stored_object(image) for image in output["gallery_images"]]

    def apply(product: ProductMaster) -> None:
        product.description = output["description"]
        product.selling_points = "\n".join(output["bullet_points"]) or None
        product.main_image, product.sub_images = main_image, sub_images
        product.crawl_status, product.crawl_error = "done", None
        _set_trace(product, "crawl", None)

    product = await session.get(ProductMaster, product_id)
    return await _apply_images(session, product, [main_image, *sub_images], apply)


async def complete_view(session: AsyncSession, product_id: int, output: dict) -> list[StoredRef]:
    """output 为 view_select 的输出，按正面、侧面、背面的顺序写入三视图参考图；侧面可能缺失。

    参考图都选自主图副图，沿用其存储对象，不另存副本。
    """
    def apply(product: ProductMaster) -> None:
        by_url = {image["url"]: image for image in (product.main_image, *product.sub_images) if image and image.get("url")}
        views = (output["front_url"], output["side_url"], output["back_url"])
        product.three_view_reference_images = [
            by_url.get(url) or {"key": None, "url": url, "type": EXTERNAL} for url in views if url
        ]
        product.three_view_side_kind = output["side_kind"]
        product.view_status, product.view_error = "done", None
        _set_trace(product, "view", None)

    product = await session.get(ProductMaster, product_id)
    return await _apply_images(session, product, [], apply)


async def complete_gen(session: AsyncSession, product_id: int, output: dict) -> list[StoredRef]:
    """output 为 three_view_gen 的输出，生成的是一张三联图，写入三视图字段；重新生成时旧图会被清理。"""
    image = _stored_object(output["image"])

    def apply(product: ProductMaster) -> None:
        product.three_view_images = [image]
        product.gen_status, product.gen_error = "done", None
        _set_trace(product, "gen", None)

    product = await session.get(ProductMaster, product_id)
    return await _apply_images(session, product, [image], apply)


@dataclass(frozen=True)
class StageFailure:
    """阶段失败的现场，input 为调用 Tool 的参数，output 为 Tool 返回的输出（失败时通常为空）。"""

    message: str
    input: dict
    output: dict | None = None
    error_code: str | None = None


async def _fail(session: AsyncSession, product_id: int, stage: str, failure: StageFailure) -> None:
    product = await session.get(ProductMaster, product_id)
    if product is None:
        return
    message = failure.message[:ERROR_MAX_LENGTH]
    setattr(product, f"{stage}_status", "failed")
    setattr(product, f"{stage}_error", message)
    _set_trace(product, stage, {
        "input": failure.input, "output": failure.output or {}, "error_code": failure.error_code, "error_message": message,
    })
    await session.flush()


async def fail_crawl(session: AsyncSession, product_id: int, failure: StageFailure) -> None:
    await _fail(session, product_id, "crawl", failure)


async def fail_view(session: AsyncSession, product_id: int, failure: StageFailure) -> None:
    await _fail(session, product_id, "view", failure)


async def fail_gen(session: AsyncSession, product_id: int, failure: StageFailure) -> None:
    await _fail(session, product_id, "gen", failure)


async def _sync_id_sequence(session: AsyncSession) -> None:
    """指定主键插入不会推进自增序列，插入后把序列对齐到当前最大 ID，避免后续新建撞主键。"""
    table = f"{SCHEMA}.{ScriptTemplate.__tablename__}"
    await session.execute(
        text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")
    )
