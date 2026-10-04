"""业务逻辑层：事务边界在调用方（get_session 依赖），这里只管业务。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok.models import Account


async def list_accounts(session: AsyncSession, limit: int) -> list[Account]:
    stmt = select(Account).order_by(Account.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def create_account(session: AsyncSession, name: str) -> Account:
    account = Account(name=name)
    session.add(account)
    await session.flush()
    return account


async def get_account(session: AsyncSession, account_id: int) -> Account | None:
    return await session.get(Account, account_id)
