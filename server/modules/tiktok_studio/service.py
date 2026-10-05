"""业务逻辑层：事务边界在调用方（get_session 依赖），这里只管业务。"""

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok_studio.models import SCHEMA, ProductMaster, ScriptTemplate
from modules.tiktok_studio.schemas import ProductMasterFields, ScriptTemplateFields


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


async def _sync_id_sequence(session: AsyncSession) -> None:
    """指定主键插入不会推进自增序列，插入后把序列对齐到当前最大 ID，避免后续新建撞主键。"""
    table = f"{SCHEMA}.{ScriptTemplate.__tablename__}"
    await session.execute(
        text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")
    )
