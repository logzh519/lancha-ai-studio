"""Tool 层：一项业务能力的完整封装。

边界见 docs/架构规范.md §3「模块内的 Tool 层」。

调用方按名字构造，不 import 具体 Tool 类：

    tool = tools.build("template_match", tools.ToolDeps(session=session))
    result = await tool.execute({"category": "top"}, ToolSettings(timeout=10, trace_id=trace_id))

新增 Tool 时在 _FACTORIES 里加一行；工厂只挑该 Tool 真正需要的依赖，保证依赖关系写在构造签名上。
"""

from collections.abc import Callable

from modules.tiktok_studio.tools.amazon_crawler import AmazonCrawlerTool
from modules.tiktok_studio.tools.base import (
    Tool,
    ToolDeps,
    ToolError,
    ToolResult,
    ToolSettings,
)
from modules.tiktok_studio.tools.template_match import TemplateMatchTool
from modules.tiktok_studio.tools.view_select import ViewSelectTool


def _require[T](value: T | None, name: str) -> T:
    if value is None:
        raise ValueError(f"ToolDeps 缺少 {name}")
    return value


# 工具注册工厂：按名字构造，不 import 具体 Tool 类
_FACTORIES: dict[str, Callable[[ToolDeps], Tool]] = {
    TemplateMatchTool.name: lambda deps: TemplateMatchTool(session=deps.session),
    AmazonCrawlerTool.name: lambda deps: AmazonCrawlerTool(storage=_require(deps.storage, "storage")),
    ViewSelectTool.name: lambda deps: ViewSelectTool(llm=_require(deps.llm, "llm")),
}


def build(name: str, deps: ToolDeps) -> Tool:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise KeyError(f"未注册的 tool：{name}，已注册：{sorted(_FACTORIES)}")
    return factory(deps)


__all__ = ["Tool", "ToolDeps", "ToolError", "ToolResult", "ToolSettings", "build"]
