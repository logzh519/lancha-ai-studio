"""Tool 基类与注册表的行为：输入校验、业务失败、未预期异常、按名字构造。"""

import pytest
from pydantic import BaseModel

from platforms.tools import (
    Tool,
    ToolDeps,
    ToolError,
    ToolRegistry,
    ToolSettings,
    require,
)

SETTINGS = ToolSettings(timeout=5.0, trace_id="trace-1")


class EchoInput(BaseModel):
    value: int


class EchoOutput(BaseModel):
    doubled: int


class EchoTool(Tool[EchoInput, EchoOutput]):
    """只在测试里使用的假 Tool，用来驱动基类的四条通路。"""

    name = "echo"
    input_model = EchoInput
    output_model = EchoOutput

    def __init__(self, *, fail_code: str | None = None, crash: bool = False) -> None:
        self._fail_code = fail_code
        self._crash = crash

    async def run(self, payload: EchoInput, settings: ToolSettings) -> EchoOutput:
        if self._crash:
            raise RuntimeError("内部 bug")
        if self._fail_code:
            raise ToolError(self._fail_code, "业务失败")
        return EchoOutput(doubled=payload.value * 2)


async def test_execute_returns_output():
    result = await EchoTool().execute({"value": 3}, SETTINGS)
    assert (result.success, result.output) == (True, {"doubled": 6})
    assert result.error_code is None


async def test_invalid_input_is_a_failed_result_not_an_exception():
    result = await EchoTool().execute({"value": "abc"}, SETTINGS)
    assert (result.success, result.error_code, result.output) == (False, "invalid_input", {})
    assert result.error_message


async def test_tool_error_becomes_failed_result():
    result = await EchoTool(fail_code="no_template_matched").execute({"value": 1}, SETTINGS)
    assert (result.success, result.error_code, result.error_message) == (
        False,
        "no_template_matched",
        "业务失败",
    )


async def test_unexpected_exception_propagates():
    """未预期异常不得被吞成失败结果，否则 bug 会伪装成普通业务失败。"""
    with pytest.raises(RuntimeError, match="内部 bug"):
        await EchoTool(crash=True).execute({"value": 1}, SETTINGS)


def test_registry_builds_registered_tool():
    registry = ToolRegistry({EchoTool.name: lambda deps: EchoTool()})
    assert isinstance(registry.build("echo", ToolDeps(session=None)), EchoTool)


def test_registry_rejects_unknown_name():
    with pytest.raises(KeyError, match="未注册的 tool"):
        ToolRegistry({}).build("nope", ToolDeps(session=None))


def test_registry_extend_keeps_parent_and_rejects_duplicates():
    parent = ToolRegistry({EchoTool.name: lambda deps: EchoTool()})
    child = parent.extend({"echo_fail": lambda deps: EchoTool(fail_code="x")})

    assert isinstance(child.build("echo", ToolDeps(session=None)), EchoTool)
    assert isinstance(child.build("echo_fail", ToolDeps(session=None)), EchoTool)
    with pytest.raises(KeyError):
        parent.build("echo_fail", ToolDeps(session=None))
    with pytest.raises(ValueError, match="echo"):
        parent.extend({"echo": lambda deps: EchoTool()})


def test_require_rejects_missing_dependency():
    with pytest.raises(ValueError, match="storage"):
        require(None, "storage")
