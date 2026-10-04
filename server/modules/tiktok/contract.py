"""对外契约：本模块唯一允许被其他模块 import 的文件，只返回冻结的 DTO，不返回 ORM 对象。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class AccountView:
    id: int
    name: str


async def get_account(session: AsyncSession, account_id: int) -> AccountView | None:
    from modules.tiktok import service

    account = await service.get_account(session, account_id)
    return None if account is None else AccountView(id=account.id, name=account.name)
