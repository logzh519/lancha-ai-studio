"""业务逻辑层：事务边界在调用方（get_session 依赖），这里只管业务。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.example.models import Item


async def list_items(session: AsyncSession, limit: int) -> list[Item]:
    stmt = select(Item).order_by(Item.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def create_item(session: AsyncSession, name: str) -> Item:
    item = Item(name=name)
    session.add(item)
    await session.flush()
    return item


async def get_item(session: AsyncSession, item_id: int) -> Item | None:
    return await session.get(Item, item_id)
