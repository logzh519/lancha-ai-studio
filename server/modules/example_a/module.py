"""模块注册入口：模块元信息的唯一来源。

权限码、菜单只在这里声明一次，前端不重复维护。
loader 会在启动时校验命名规范（权限码以模块名开头、菜单路径以 /模块名 开头等）。
"""

from modules.example_a.api import router
from modules.example_a.worker import LOOPS
from platforms.contract import MenuDef, ModuleSpec, PermissionDef

MODULE = ModuleSpec(
    name="example_a",
    title="Module System A",
    version="0.1.0",
    router=router,
    permissions=(
        PermissionDef("example_a:item:view", "查看条目"),
        PermissionDef("example_a:item:create", "创建条目"),
    ),
    menus=(
        MenuDef("A 条目", "/example_a/items", icon="list", order=10, permission="example_a:item:view"),
    ),
    loops=LOOPS,
)
