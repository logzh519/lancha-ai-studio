"""模块与平台之间的契约：每个模块在 modules/<模块名>/module.py 中导出 MODULE = ModuleSpec(...)。

ModuleSpec 是模块元信息的唯一来源——路由、权限点、菜单、后台循环都在这里声明一次，
前端不重复维护菜单和权限清单，登录后调 GET /api/modules 取。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import APIRouter

LifecycleHook = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class PermissionDef:
    code: str                       # 格式 <模块名>:<资源>:<动作>，如 example:item:create
    name: str


@dataclass(frozen=True)
class MenuDef:
    title: str
    path: str                       # 前端路由，必须以 /<模块名> 开头
    icon: str = ""
    order: int = 0
    permission: str | None = None   # 命中该权限码的用户才能看到，须在本模块 permissions 中声明
    parent: str | None = None       # 父菜单的 path，为空表示一级菜单


@dataclass(frozen=True)
class LoopContext:
    """平台传给后台循环的运行上下文。"""
    module: str
    name: str
    stopping: asyncio.Event                 # 收到停机信号后被设置，循环应尽快退出
    logger: logging.Logger                  # 名为 worker.<模块名>.<循环名>

    async def sleep(self, seconds: float) -> bool:
        """等待 seconds 秒；期间收到停机信号则提前返回 False，否则返回 True。"""
        try:
            await asyncio.wait_for(self.stopping.wait(), seconds)
        except TimeoutError:
            return True
        return False


LoopRunner = Callable[[LoopContext], Awaitable[None]]


@dataclass(frozen=True)
class BackgroundLoop:
    name: str                               # 模块内唯一，全局名为 <模块名>.<name>
    run: LoopRunner                         # 抛异常会被退避重启，正常返回视为该循环结束
    stop_timeout: float = 30.0              # 停机信号发出后等待退出的上限，超时则取消
    singleton: bool = False                 # 多副本部署时全局只运行一份（PostgreSQL advisory lock）


@dataclass(frozen=True)
class ModuleSpec:
    name: str                                               # 必须与模块目录名一致，路由挂到 /api/<name>
    title: str                                              # 菜单分组名
    version: str = "0.1.0"
    depends_on: tuple[str, ...] = ()                        # 依赖的其他模块名，禁止成环
    router: APIRouter | None = None
    permissions: tuple[PermissionDef, ...] = ()
    menus: tuple[MenuDef, ...] = ()
    on_startup: LifecycleHook | None = None                 # 进程启动时按加载顺序调用（API 与每个 worker 各一次）
    on_shutdown: LifecycleHook | None = None                # 进程关闭时按加载的逆序调用
    subscriptions: dict[str, tuple[Callable, ...]] = field(default_factory=dict)  # 事件名 -> 处理函数
    loops: tuple[BackgroundLoop, ...] = ()                  # 后台循环，只在 python main.py worker 中运行
