"""对外契约：本模块唯一允许被其他模块 import 的文件。

只返回冻结的 DTO，不返回 ORM 对象——一旦把 ORM 对象交出去，调用方就能顺着关系遍历到本模块的表结构，
边界就形同虚设了。
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from modules.example import service


@dataclass(frozen=True)
class ItemView:
    id: int
    name: str


async def get_item(session: AsyncSession, item_id: int) -> ItemView | None:
    item = await service.get_item(session, item_id)
    return None if item is None else ItemView(id=item.id, name=item.name)
