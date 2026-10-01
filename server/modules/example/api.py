"""路由层：只做参数校验和调用 service，不写业务逻辑。

路由自动挂载到 /api/example 下，不要在这里重复写模块前缀。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from modules.example import service
from modules.example.config import get_settings
from platforms.auth.dependencies import require
from platforms.db import get_session

router = APIRouter()


class ItemOut(BaseModel):
    id: int
    name: str


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


@router.get("/items", response_model=list[ItemOut], dependencies=[Depends(require("example:item:view"))])
async def list_items(session: AsyncSession = Depends(get_session)):
    items = await service.list_items(session, get_settings().page_size)
    return [ItemOut(id=item.id, name=item.name) for item in items]


@router.post("/items", response_model=ItemOut, dependencies=[Depends(require("example:item:create"))])
async def create_item(payload: ItemCreate, session: AsyncSession = Depends(get_session)):
    item = await service.create_item(session, payload.name)
    return ItemOut(id=item.id, name=item.name)
