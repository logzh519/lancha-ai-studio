"""业务逻辑层：事务边界在调用方（get_session 依赖），这里只管业务。"""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok.models import SCHEMA, ScriptTemplate
from modules.tiktok.schemas import ScriptTemplateFields


async def list_script_templates(
    session: AsyncSession, offset: int, limit: int, keyword: str | None = None
) -> tuple[list[ScriptTemplate], int]:
    conditions = []
    if keyword:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(ScriptTemplate.name.ilike(f"%{escaped}%", escape="\\"))
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


async def _sync_id_sequence(session: AsyncSession) -> None:
    """指定主键插入不会推进自增序列，插入后把序列对齐到当前最大 ID，避免后续新建撞主键。"""
    table = f"{SCHEMA}.{ScriptTemplate.__tablename__}"
    await session.execute(
        text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")
    )
