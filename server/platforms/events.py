"""进程内事件总线：模块之间"通知型"通信的唯一通道。

事件名格式 <模块名>.<事件>，载荷用模块 contract.py 里定义的冻结 dataclass。
发布方不关心谁在消费，也拿不到处理结果；需要拿结果的场景改用对方 contract.py 的函数。

当前实现是同进程同步派发，失败只记日志不影响发布方。
以后要可靠投递时，把 publish 换成写 outbox 表 + 后台投递，订阅方代码不用改。
"""

import inspect
import logging
from collections import defaultdict
from collections.abc import Callable

logger = logging.getLogger("platform.events")

_handlers: dict[str, list[Callable]] = defaultdict(list)


def subscribe(event: str, handler: Callable) -> None:
    _handlers[event].append(handler)


def clear() -> None:
    """清空订阅（仅供测试与模块重新加载使用）。"""
    _handlers.clear()


async def publish(event: str, payload) -> None:
    for handler in _handlers.get(event, ()):
        try:
            result = handler(payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("事件 %s 的处理函数 %s 执行失败", event, getattr(handler, "__qualname__", handler))
