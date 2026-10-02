"""模块与平台之间的契约：每个模块在 modules/<模块名>/module.py 中导出 MODULE = ModuleSpec(...)。

ModuleSpec 是模块元信息的唯一来源——路由、权限点、菜单都在这里声明一次，
前端不重复维护菜单和权限清单，登录后调 GET /api/modules 取。
"""

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
class ModuleSpec:
    name: str                                               # 必须与模块目录名一致，路由挂到 /api/<name>
    title: str                                              # 菜单分组名
    version: str = "0.1.0"
    depends_on: tuple[str, ...] = ()                        # 依赖的其他模块名，禁止成环
    router: APIRouter | None = None
    permissions: tuple[PermissionDef, ...] = ()
    menus: tuple[MenuDef, ...] = ()
    on_startup: LifecycleHook | None = None                 # 网关启动时按加载顺序调用
    on_shutdown: LifecycleHook | None = None                # 网关关闭时按加载的逆序调用
    subscriptions: dict[str, tuple[Callable, ...]] = field(default_factory=dict)  # 事件名 -> 处理函数
