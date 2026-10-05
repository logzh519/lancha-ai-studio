"""按名字构造 Tool 的注册表。

工厂只挑该 Tool 真正需要的依赖，保证依赖关系写在构造签名上；调用方按名字构造，不 import 具体 Tool 类。
"""

from collections.abc import Callable, Mapping

from platforms.tools.base import Tool, ToolDeps

type ToolFactory = Callable[[ToolDeps], Tool]


def require[T](value: T | None, name: str) -> T:
    if value is None:
        raise ValueError(f"ToolDeps 缺少 {name}")
    return value


class ToolRegistry:
    def __init__(self, factories: Mapping[str, ToolFactory]) -> None:
        self._factories = dict(factories)

    def extend(self, factories: Mapping[str, ToolFactory]) -> "ToolRegistry":
        """在当前注册表基础上追加 Tool，返回新注册表；不允许覆盖已注册的名字。"""
        duplicated = sorted(self._factories.keys() & factories.keys())
        if duplicated:
            raise ValueError(f"tool 名字重复注册：{duplicated}")
        return ToolRegistry({**self._factories, **factories})

    def build(self, name: str, deps: ToolDeps) -> Tool:
        factory = self._factories.get(name)
        if factory is None:
            raise KeyError(f"未注册的 tool：{name}，已注册：{sorted(self._factories)}")
        return factory(deps)
