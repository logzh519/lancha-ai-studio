"""Tool 框架与跨模块通用的 Tool。边界见 docs/架构规范.md §3「Tool 层」。

platform_tools 登记平台自带的通用 Tool；模块用 platform_tools.extend({...}) 追加本模块特有的 Tool。
"""

from platforms.tools.amazon_crawler import AmazonCrawlerTool
from platforms.tools.base import (
    Tool,
    ToolDeps,
    ToolError,
    ToolResult,
    ToolSettings,
    retry_async,
)
from platforms.tools.registry import ToolFactory, ToolRegistry, require
from platforms.tools.view_select import ViewSelectTool

platform_tools = ToolRegistry({
    AmazonCrawlerTool.name: lambda deps: AmazonCrawlerTool(storage=require(deps.storage, "storage")),
    ViewSelectTool.name: lambda deps: ViewSelectTool(llm=require(deps.llm, "llm")),
})

__all__ = [
    "Tool",
    "ToolDeps",
    "ToolError",
    "ToolFactory",
    "ToolRegistry",
    "ToolResult",
    "ToolSettings",
    "platform_tools",
    "require",
    "retry_async",
]
