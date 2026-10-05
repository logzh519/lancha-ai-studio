"""按类目从爆款脚本模板库里挑一条正式模板。"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok_studio import service
from modules.tiktok_studio.schemas import Category
from platforms.tools import Tool, ToolError, ToolSettings


class TemplateMatchInput(BaseModel):
    category: Category


class TemplateMatchOutput(BaseModel):
    template_id: int
    name: str
    category: Category
    duration_seconds: int
    content: str
    version: str


class TemplateMatchTool(Tool[TemplateMatchInput, TemplateMatchOutput]):
    """候选池 = 全品类模板 + 入参类目的模板，从中随机取一条。

    随机意味着重跑可能换一条模板；输出带 template_id，用了哪个模板始终可查。
    """

    name = "template_match"
    input_model = TemplateMatchInput
    output_model = TemplateMatchOutput

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def run(self, payload: TemplateMatchInput, settings: ToolSettings) -> TemplateMatchOutput:
        template = await service.pick_script_template(self._session, payload.category)
        if template is None:
            raise ToolError("no_template_matched", f"类目 {payload.category} 下没有可用的正式模板")
        return TemplateMatchOutput(
            template_id=template.id,
            name=template.name,
            category=template.category,
            duration_seconds=template.duration_seconds,
            content=template.content,
            version=template.version,
        )
