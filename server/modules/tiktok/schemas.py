"""脚本模板的字段取值与校验规则，api 与导入脚本共用。"""

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["all", "top", "bottom"]
Status = Literal["formal", "test"]


class ScriptTemplateFields(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: Category
    duration_seconds: int = Field(gt=0)
    content: str = Field(min_length=1)
    status: Status = "test"
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$", max_length=32)
    reference_video_url: str | None = Field(default=None, max_length=2048)
