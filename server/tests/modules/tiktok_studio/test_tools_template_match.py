"""template_match 的匹配规则：正式模板、全品类并入候选池、随机取一条。"""

import pytest

from modules.tiktok_studio import service
from modules.tiktok_studio.schemas import ScriptTemplateFields
from modules.tiktok_studio.tools.base import ToolSettings
from modules.tiktok_studio.tools.template_match import TemplateMatchTool

pytestmark = pytest.mark.db

SETTINGS = ToolSettings(timeout=5.0, trace_id="trace-1")
COMMON = {"duration_seconds": 15, "content": "分镜正文", "version": "1.0.0", "reference_video_url": None}


async def _template(session, name: str, category: str, status: str = "formal"):
    fields = ScriptTemplateFields(name=name, category=category, status=status, **COMMON)
    return await service.create_script_template(session, fields, created_by=None)


async def _run(session, category: str):
    return await TemplateMatchTool(session=session).execute({"category": category}, SETTINGS)


async def test_other_categories_are_excluded(session):
    await _template(session, "上衣脚本", "top")
    await _template(session, "下衣脚本", "bottom")

    result = await _run(session, "top")

    assert result.success is True
    assert result.output["name"] == "上衣脚本"


async def test_all_category_templates_join_the_pool(session):
    await _template(session, "通用脚本", "all")

    result = await _run(session, "top")

    assert result.success is True
    assert result.output["name"] == "通用脚本"


async def test_test_status_templates_are_excluded(session):
    await _template(session, "正式脚本", "top")
    await _template(session, "测试脚本", "top", status="test")

    result = await _run(session, "top")

    assert result.output["name"] == "正式脚本"


async def test_empty_pool_returns_tool_error(session):
    await _template(session, "下衣脚本", "bottom")

    result = await _run(session, "top")

    assert (result.success, result.error_code) == (False, "no_template_matched")
    assert result.output == {}


async def test_duration_comes_from_the_matched_template(session):
    fields = ScriptTemplateFields(
        name="长脚本", category="top", status="formal", duration_seconds=60,
        content="分镜正文", version="1.0.0", reference_video_url=None,
    )
    await service.create_script_template(session, fields, created_by=None)

    result = await _run(session, "top")

    assert result.output["duration_seconds"] == 60


async def test_pick_is_random_across_the_pool(session):
    """两条都在候选池里时，多次调用应当都出现过。漏选一条的概率约为 2 × (1/2)^30。"""
    await _template(session, "候选甲", "top")
    await _template(session, "候选乙", "all")

    names = {(await _run(session, "top")).output["name"] for _ in range(30)}

    assert names == {"候选甲", "候选乙"}
