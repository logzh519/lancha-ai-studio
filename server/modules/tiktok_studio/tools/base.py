"""Tool 契约：给它业务参数，它还你可以直接使用的业务结果。

Tool 的边界不是「不碰存储」，而是「不碰编排」：允许访问基础设施服务与业务数据源，
禁止读写任务、节点、批次。Tool 内可以对瞬时故障做有限次重试（retry_async），耗尽后再抛 ToolError。
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.llm import AsyncLLMClient
from platforms.storage import ObjectStorage

logger = logging.getLogger("tiktok_studio.tools")


@dataclass(frozen=True)
class ToolSettings:
    """调用方注入的运行期参数。Tool 只读，不得据此推断编排逻辑。"""

    timeout: float      # 发起外部调用时由 Tool 自行应用；纯本地 Tool 忽略它
    trace_id: str       # 日志关联用


@dataclass(frozen=True)
class ToolDeps:
    """调用方能提供的基础设施与业务数据源全集。字段只在有真实来源时新增。"""

    session: AsyncSession
    storage: ObjectStorage | None = None    # 缺省时依赖它的 Tool 在 build() 时报错
    llm: AsyncLLMClient | None = None


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: dict
    error_code: str | None = None
    error_message: str | None = None


class ToolError(Exception):
    """业务失败。Tool 内部重试耗尽后才抛出，code 供调用方判定是否整体重跑。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    *,
    delays: Sequence[float],
    retry_if: Callable[[Exception], bool],
    label: str,
    trace_id: str,
) -> T:
    """执行 operation，失败且 retry_if 为真时按 delays 依次等待后重试；delays 的长度即最大重试次数。"""
    for attempt in range(len(delays) + 1):
        try:
            return await operation()
        except Exception as exc:
            if attempt >= len(delays) or not retry_if(exc):
                raise
            logger.warning(
                "[%s] %s 失败（第 %d/%d 次），%.0fs 后重试：%s",
                trace_id, label, attempt + 1, len(delays) + 1, delays[attempt], exc,
            )
            await asyncio.sleep(delays[attempt])
    raise AssertionError("unreachable")


class Tool[In: BaseModel, Out: BaseModel](ABC):
    """依赖一律由子类在 __init__ 中显式声明并构造注入，不在内部读全局配置。"""

    name: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def run(self, payload: In, settings: ToolSettings) -> Out:
        """业务能力本体。失败抛 ToolError，不返回错误码。"""

    async def execute(self, payload: dict, settings: ToolSettings) -> ToolResult:
        """调用方入口：校验输入、调用 run、包成 ToolResult。

        输出不单独校验：run 的返回值已经是 Out 实例，构造时就已合法。
        非 ToolError 的异常不捕获，交给调用方处理。
        """
        try:
            parsed = self.input_model.model_validate(payload)
        except ValidationError as exc:
            return ToolResult(False, {}, "invalid_input", str(exc))
        try:
            output = await self.run(parsed, settings)
        except ToolError as exc:
            return ToolResult(False, {}, exc.code, exc.message)
        return ToolResult(True, output.model_dump(mode="json"))
