"""脚本模板与商品资产的字段取值与校验规则，api 与导入脚本共用。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Category = Literal["all", "top", "bottom"]
Status = Literal["formal", "test"]
ImportStatus = Literal["pending", "running", "done", "failed"]
EXTERNAL = "external"


class StoredObject(BaseModel):
    """图片资源。type 为存储类型（tos / obs）时 key 指向对象存储；为 external 时是外部链接，没有 key，不由本模块清理。"""

    key: str | None = Field(default=None, max_length=1024)
    url: str | None = Field(default=None, max_length=2048)     # 私有 ACL 的存储对象没有公开地址
    type: str = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def _check(self) -> "StoredObject":
        if self.type == EXTERNAL:
            if not self.url or self.key is not None:
                raise ValueError("外部链接必须提供 url，且不能带 key")
        elif not self.key:
            raise ValueError(f"存储类型 {self.type} 的资源必须提供 key")
        return self


class ScriptTemplateFields(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: Category
    duration_seconds: int = Field(gt=0)
    content: str = Field(min_length=1)
    status: Status = "test"
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$", max_length=32)
    reference_video_url: str | None = Field(default=None, max_length=2048)


class ProductMasterFields(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    asin: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=64)
    store: str | None = Field(default=None, max_length=128)
    pid: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=64)
    description: str | None = None
    selling_points: str | None = None
    main_image: StoredObject | None = None
    sub_images: list[StoredObject] = []
    three_view_images: list[StoredObject] = Field(default=[], max_length=1)     # 生成的是一张三联图
    three_view_reference_images: list[StoredObject] = Field(default=[], max_length=3)

    @model_validator(mode="after")
    def _check_references(self) -> "ProductMasterFields":
        """三视图参考图只能选自主图或副图，与自动识别的候选范围一致。"""
        candidates = [self.main_image, *self.sub_images]
        if any(image not in candidates for image in self.three_view_reference_images):
            raise ValueError("三视图参考图只能从主图或副图中选择")
        return self


class TaskOrderPreviewRequest(BaseModel):
    skus: list[str] = Field(min_length=1, max_length=50)


class TaskOrderPreviewItem(BaseModel):
    sku: str
    asin: str | None
    color: str | None
    shop: str | None
    warnings: list[str] = Field(default_factory=list)


class TaskOrderPreviewResponse(BaseModel):
    items: list[TaskOrderPreviewItem]


class TaskOrderItem(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    asin: str = Field(min_length=1, max_length=32)
    color: str | None = Field(default=None, max_length=64)
    shop: str | None = Field(default=None, max_length=128)


class BatchCreateRequest(BaseModel):
    request_id: UUID
    name: str = Field(min_length=1, max_length=255)
    pipeline_key: Literal["video_gen_15s"] = "video_gen_15s"
    items: list[TaskOrderItem] = Field(min_length=1, max_length=2000)
    note: str | None = None


class BatchCreateResponse(BaseModel):
    id: str
    name: str
    pipeline_key: str
    status: str
    total_tasks: int
    created_by: int


class BatchSummary(BaseModel):
    id: str
    name: str
    pipeline_key: str
    status: str
    total_tasks: int
    note: str | None
    created_at: datetime


class BatchPage(BaseModel):
    items: list[BatchSummary]
    total: int


class TaskSummary(BaseModel):
    id: str
    batch_id: str
    biz_key: str
    context: dict
    status: str
    created_at: datetime


class TaskPage(BaseModel):
    items: list[TaskSummary]
    total: int
