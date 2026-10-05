"""脚本模板与商品资产的字段取值与校验规则，api 与导入脚本共用。"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Category = Literal["all", "top", "bottom"]
Status = Literal["formal", "test"]
ImportStatus = Literal["pending", "running", "done", "failed"]
ImageUrl = Annotated[str, Field(min_length=1, max_length=2048)]


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
    main_image_url: str | None = Field(default=None, max_length=2048)
    sub_images: list[ImageUrl] = []
    three_view_images: list[ImageUrl] = Field(default=[], max_length=3)
    three_view_reference_images: list[ImageUrl] = Field(default=[], max_length=3)
