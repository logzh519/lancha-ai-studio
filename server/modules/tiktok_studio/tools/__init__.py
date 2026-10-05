"""本模块可用的 Tool：平台通用 Tool（platforms.tools.platform_tools）加本模块特有的 Tool。

边界见 docs/架构规范.md §3「Tool 层」。调用方按名字构造，不 import 具体 Tool 类：

    tool = tools.build("template_match", tools.ToolDeps(session=session))
    result = await tool.execute({"category": "top"}, ToolSettings(timeout=10, trace_id=trace_id))

本模块新增 Tool 时在 extend 里加一行；工厂只挑该 Tool 真正需要的依赖，保证依赖关系写在构造签名上。
"""

from modules.tiktok_studio.tools.template_match_tool import TemplateMatchTool
from platforms.tools import (
    Tool,
    ToolDeps,
    ToolError,
    ToolResult,
    ToolSettings,
    platform_tools,
)

_REGISTRY = platform_tools.extend({
    TemplateMatchTool.name: lambda deps: TemplateMatchTool(session=deps.session),
})

build = _REGISTRY.build

__all__ = ["Tool", "ToolDeps", "ToolError", "ToolResult", "ToolSettings", "build"]
