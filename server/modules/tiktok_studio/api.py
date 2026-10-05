"""路由层：只做参数校验和调用 service，不写业务逻辑。

路由自动挂载到 /api/tiktok_studio 下，不要在这里重复写模块前缀。
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok_studio import importing, service
from modules.tiktok_studio.models import ProductMaster, ScriptTemplate
from modules.tiktok_studio.schemas import (
    BatchPage,
    BatchCreateRequest,
    BatchCreateResponse,
    BatchSummary,
    Category,
    ImportStatus,
    ProductMasterFields,
    ScriptTemplateFields,
    Status,
    StoredObject,
    TaskOrderPreviewRequest,
    TaskOrderPreviewResponse,
    TaskPage,
    TaskSummary,
)
from platforms.auth.dependencies import require
from platforms.auth.principal import Principal
from platforms.db import get_session

router = APIRouter()


@router.post(
    "/orders/preview",
    response_model=TaskOrderPreviewResponse,
)
async def preview_task_order(
    payload: TaskOrderPreviewRequest,
    principal: Principal = Depends(require("tiktok_studio:order:preview")),
    session: AsyncSession = Depends(get_session),
):
    try:
        items = await service.preview_task_order(session, payload.skus, principal.user_id)
    except service.InvalidTaskOrder as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return TaskOrderPreviewResponse(items=items)


@router.post(
    "/batches",
    response_model=BatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_video_batch(
    payload: BatchCreateRequest,
    principal: Principal = Depends(require("tiktok_studio:batch:create")),
    session: AsyncSession = Depends(get_session),
):
    try:
        batch = await service.create_video_batch(session, payload, principal.user_id)
    except service.IdempotencyConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except service.InvalidTaskOrder as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    await session.commit()
    return BatchCreateResponse(
        id=batch.id,
        name=batch.name,
        pipeline_key=batch.pipeline_key,
        status=batch.status,
        total_tasks=batch.total_tasks,
        created_by=batch.created_by,
    )


@router.get(
    "/batches",
    response_model=BatchPage,
)
async def list_video_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    principal: Principal = Depends(require("tiktok_studio:batch:create")),
    session: AsyncSession = Depends(get_session),
):
    batches, total = await service.list_video_batches(
        session, principal.user_id, (page - 1) * page_size, page_size
    )
    return BatchPage(
        items=[BatchSummary.model_validate(batch, from_attributes=True) for batch in batches],
        total=total,
    )


@router.get(
    "/batches/{batch_id}/tasks",
    response_model=TaskPage,
)
async def list_batch_tasks(
    batch_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    principal: Principal = Depends(require("tiktok_studio:batch:create")),
    session: AsyncSession = Depends(get_session),
):
    result = await service.list_batch_tasks(
        session, batch_id, principal.user_id, (page - 1) * page_size, page_size
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "批次不存在")
    tasks, total = result
    return TaskPage(
        items=[TaskSummary.model_validate(task, from_attributes=True) for task in tasks],
        total=total,
    )


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


class StageTrace(BaseModel):
    """导入阶段失败的现场，键为 crawl / view / gen。"""

    input: dict
    output: dict
    error_code: str | None
    error_message: str


class ProductMasterSummary(BaseModel):
    id: int
    sku: str
    asin: str | None
    color: str | None
    store: str | None
    pid: str | None
    category: str | None
    main_image: StoredObject | None
    crawl_status: ImportStatus | None
    crawl_error: str | None
    view_status: ImportStatus | None
    view_error: str | None
    gen_status: ImportStatus | None
    gen_error: str | None
    import_trace: dict[str, StageTrace]
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class ProductMasterPage(BaseModel):
    items: list[ProductMasterSummary]
    total: int


class ProductMasterOut(ProductMasterSummary):
    description: str | None
    selling_points: str | None
    sub_images: list[StoredObject]
    three_view_images: list[StoredObject]
    three_view_reference_images: list[StoredObject]


class ProductImportRequest(BaseModel):
    skus: list[Annotated[str, Field(max_length=64)]] = Field(min_length=1, max_length=50)


class ProductImportFailure(BaseModel):
    sku: str
    message: str


class ProductImportResult(BaseModel):
    created: list[ProductMasterSummary]
    skipped: int
    failed: list[ProductImportFailure]


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
    try:
        product = await service.create_product_master(session, payload, created_by=principal.user_id)
    except service.UnknownStoredObject as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    await session.commit()
    return ProductMasterOut.model_validate(product, from_attributes=True)


@router.post("/product-masters/import", response_model=ProductImportResult)
async def import_product_masters(
    payload: ProductImportRequest,
    principal: Principal = Depends(require("tiktok_studio:product_master:create")),
    session: AsyncSession = Depends(get_session),
):
    skus = importing.normalize_skus(payload.skus)
    if not skus:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "请至少填写一个货号")
    result = await importing.import_skus(session, skus, created_by=principal.user_id)
    await session.commit()
    return ProductImportResult(
        created=[ProductMasterSummary.model_validate(p, from_attributes=True) for p in result.created],
        skipped=result.skipped,
        failed=[ProductImportFailure(sku=f.sku, message=f.message) for f in result.failed],
    )


@router.post(
    "/product-masters/{product_id}/retry-import",
    response_model=ProductMasterOut,
    dependencies=[Depends(require("tiktok_studio:product_master:create"))],
)
async def retry_product_import(product_id: int, session: AsyncSession = Depends(get_session)):
    product = await _get_product_or_404(session, product_id)
    if not await service.retry_product_import(session, product):
        raise HTTPException(status.HTTP_409_CONFLICT, f"商品 {product_id} 没有失败的导入阶段")
    await session.commit()
    return ProductMasterOut.model_validate(product, from_attributes=True)


@router.post(
    "/product-masters/{product_id}/regenerate-three-view",
    response_model=ProductMasterOut,
    dependencies=[Depends(require("tiktok_studio:product_master:update"))],
)
async def regenerate_three_view(product_id: int, session: AsyncSession = Depends(get_session)):
    product = await _get_product_or_404(session, product_id)
    try:
        await service.regenerate_three_view(session, product)
    except service.RegenerateUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
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
    try:
        product, orphans = await service.update_product_master(
            session, await _get_product_or_404(session, product_id), payload,
        )
    except service.UnknownStoredObject as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    await session.commit()
    await service.purge_objects(orphans)
    return ProductMasterOut.model_validate(product, from_attributes=True)


IMAGE_MAX_BYTES = 10 * 1024 * 1024
# 三视图参考图只能选自主图副图，不接受上传
ImageField = Literal["main_image", "sub_images", "three_view_images"]


@router.post(
    "/product-masters/{product_id}/images/{field}",
    response_model=StoredObject,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require("tiktok_studio:product_master:update"))],
)
async def upload_product_image(
    product_id: int,
    field: ImageField,
    request: Request,
    content_type: str = Header(),
    session: AsyncSession = Depends(get_session),
):
    """请求体为图片原始字节，Content-Type 标明图片格式。"""
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime not in service.IMAGE_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "仅支持 JPG、PNG、WebP、GIF 图片")
    content = await request.body()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "图片内容为空")
    if len(content) > IMAGE_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "图片不能超过 10MB")
    product = await _get_product_or_404(session, product_id)
    image, orphans = await service.upload_product_image(session, product, field, content, mime)
    await session.commit()
    await service.purge_objects(orphans)
    return image


@router.delete(
    "/product-masters/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require("tiktok_studio:product_master:delete"))],
)
async def delete_product_master(product_id: int, session: AsyncSession = Depends(get_session)):
    orphans = await service.delete_product_master(session, await _get_product_or_404(session, product_id))
    await session.commit()
    await service.purge_objects(orphans)
