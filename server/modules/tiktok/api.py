"""路由层：只做参数校验和调用 service，不写业务逻辑。

路由自动挂载到 /api/tiktok 下，不要在这里重复写模块前缀。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok import service
from modules.tiktok.config import get_settings
from platforms.auth.dependencies import require
from platforms.db import get_session

router = APIRouter()


class AccountOut(BaseModel):
    id: int
    name: str


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


@router.get("/accounts", response_model=list[AccountOut], dependencies=[Depends(require("tiktok:account:view"))])
async def list_accounts(session: AsyncSession = Depends(get_session)):
    accounts = await service.list_accounts(session, get_settings().page_size)
    return [AccountOut(id=account.id, name=account.name) for account in accounts]


@router.post("/accounts", response_model=AccountOut, dependencies=[Depends(require("tiktok:account:create"))])
async def create_account(payload: AccountCreate, session: AsyncSession = Depends(get_session)):
    account = await service.create_account(session, payload.name)
    await session.commit()
    return AccountOut(id=account.id, name=account.name)
