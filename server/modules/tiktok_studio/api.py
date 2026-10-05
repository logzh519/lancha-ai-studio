"""路由层：只做参数校验和调用 service，不写业务逻辑。

路由自动挂载到 /api/tiktok_studio 下，不要在这里重复写模块前缀。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok_studio import service
from modules.tiktok_studio.models import ProductMaster, ScriptTemplate
from modules.tiktok_studio.schemas import (
    Category,
    ProductMasterFields,
    ScriptTemplateFields,
    Status,
)
from platforms.auth.dependencies import require
from platforms.auth.principal import Principal
from platforms.db import get_session

router = APIRouter()


class ScriptTemplateSummary(BaseModel):
    id: int
    name: str
    category: Category
    duration_seconds: int
    status: Status
    version: str
    reference_video_url: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class ScriptTemplatePage(BaseModel):
    items: list[ScriptTemplateSummary]
    total: int


class ScriptTemplateOut(ScriptTemplateSummary):
    content: str


async def _get_or_404(session: AsyncSession, template_id: int) -> ScriptTemplate:
    template = await service.get_script_template(session, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"脚本模板 {template_id} 不存在")
    return template


@router.get(
    "/script-templates",
    response_model=ScriptTemplatePage,
    dependencies=[Depends(require("tiktok_studio:script_template:view"))],
)
async def list_script_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=128),
    session: AsyncSession = Depends(get_session),
):
    offset = (page - 1) * page_size
    templates, total = await service.list_script_templates(session, offset, page_size, (keyword or "").strip())
    items = [ScriptTemplateSummary.model_validate(t, from_attributes=True) for t in templates]
    return ScriptTemplatePage(items=items, total=total)


@router.get(
    "/script-templates/{template_id}",
    response_model=ScriptTemplateOut,
    dependencies=[Depends(require("tiktok_studio:script_template:view"))],
)
async def get_script_template(template_id: int, session: AsyncSession = Depends(get_session)):
    return ScriptTemplateOut.model_validate(await _get_or_404(session, template_id), from_attributes=True)


@router.post("/script-templates", response_model=ScriptTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_script_template(
    payload: ScriptTemplateFields,
    principal: Principal = Depends(require("tiktok_studio:script_template:create")),
    session: AsyncSession = Depends(get_session),
):
    template = await service.create_script_template(session, payload, created_by=principal.user_id)
    await session.commit()
    return ScriptTemplateOut.model_validate(template, from_attributes=True)


@router.put(
    "/script-templates/{template_id}",
    response_model=ScriptTemplateOut,
    dependencies=[Depends(require("tiktok_studio:script_template:update"))],
)
async def update_script_template(
    template_id: int, payload: ScriptTemplateFields, session: AsyncSession = Depends(get_session)
):
    template = await service.update_script_template(session, await _get_or_404(session, template_id), payload)
    await session.commit()
    return ScriptTemplateOut.model_validate(template, from_attributes=True)


@router.delete(
    "/script-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require("tiktok_studio:script_template:delete"))],
)
async def delete_script_template(template_id: int, session: AsyncSession = Depends(get_session)):
    await service.delete_script_template(session, await _get_or_404(session, template_id))
    await session.commit()


class ProductMasterSummary(BaseModel):
    id: int
    sku: str
    asin: str | None
    color: str | None
    store: str | None
    pid: str | None
    category: str | None
    main_image_url: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class ProductMasterPage(BaseModel):
    items: list[ProductMasterSummary]
    total: int


class ProductMasterOut(ProductMasterSummary):
    description: str | None
    selling_points: str | None
    sub_images: list[str]
    three_view_images: list[str]
    three_view_reference_images: list[str]


async def _get_product_or_404(session: AsyncSession, product_id: int) -> ProductMaster:
    product = await service.get_product_master(session, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"商品 {product_id} 不存在")
    return product


@router.get(
    "/product-masters",
    response_model=ProductMasterPage,
    dependencies=[Depends(require("tiktok_studio:product_master:view"))],
)
async def list_product_masters(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=128),
    session: AsyncSession = Depends(get_session),
):
    offset = (page - 1) * page_size
    products, total = await service.list_product_masters(session, offset, page_size, (keyword or "").strip())
    items = [ProductMasterSummary.model_validate(p, from_attributes=True) for p in products]
    return ProductMasterPage(items=items, total=total)


@router.get(
    "/product-masters/{product_id}",
    response_model=ProductMasterOut,
    dependencies=[Depends(require("tiktok_studio:product_master:view"))],
)
async def get_product_master(product_id: int, session: AsyncSession = Depends(get_session)):
    return ProductMasterOut.model_validate(await _get_product_or_404(session, product_id), from_attributes=True)


@router.post("/product-masters", response_model=ProductMasterOut, status_code=status.HTTP_201_CREATED)
async def create_product_master(
    payload: ProductMasterFields,
    principal: Principal = Depends(require("tiktok_studio:product_master:create")),
    session: AsyncSession = Depends(get_session),
):
    product = await service.create_product_master(session, payload, created_by=principal.user_id)
    await session.commit()
    return ProductMasterOut.model_validate(product, from_attributes=True)


@router.put(
    "/product-masters/{product_id}",
    response_model=ProductMasterOut,
    dependencies=[Depends(require("tiktok_studio:product_master:update"))],
)
async def update_product_master(
    product_id: int, payload: ProductMasterFields, session: AsyncSession = Depends(get_session)
):
    product = await service.update_product_master(session, await _get_product_or_404(session, product_id), payload)
    await session.commit()
    return ProductMasterOut.model_validate(product, from_attributes=True)


@router.delete(
    "/product-masters/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require("tiktok_studio:product_master:delete"))],
)
async def delete_product_master(product_id: int, session: AsyncSession = Depends(get_session)):
    await service.delete_product_master(session, await _get_product_or_404(session, product_id))
    await session.commit()
