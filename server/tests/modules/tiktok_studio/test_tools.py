"""本模块 Tool 注册表：继承平台通用 Tool，并追加本模块特有的 Tool。"""

from types import SimpleNamespace

import pytest

from modules.tiktok_studio import tools
from modules.tiktok_studio.tools.template_match import TemplateMatchTool
from platforms.tools.amazon_crawler import AmazonCrawlerTool
from platforms.tools.view_select import ViewSelectTool


@pytest.mark.db
async def test_build_constructs_registered_tool(session):
    tool = tools.build("template_match", tools.ToolDeps(session=session))

    assert isinstance(tool, TemplateMatchTool)
    assert tool.name == "template_match"


def test_build_rejects_unknown_name():
    with pytest.raises(KeyError, match="未注册的 tool"):
        tools.build("nope", tools.ToolDeps(session=None))


def test_platform_tools_are_available():
    deps = tools.ToolDeps(session=None, storage=SimpleNamespace(), llm=SimpleNamespace())
    assert isinstance(tools.build("amazon_crawler", deps), AmazonCrawlerTool)
    assert isinstance(tools.build("view_select", deps), ViewSelectTool)
