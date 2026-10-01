"""平台自身的权限码与菜单。

业务模块在 module.py 里声明，平台没有 module.py，所以单独放这里，
由 registry.all_permissions() 并入同步列表——不并入的话 sync_permissions 会把它们当成
「模块里已删除的权限点」连同角色绑定一起删掉。
"""

from platforms.contract import MenuDef, PermissionDef

PLATFORM_MODULE_NAME = "platform"

PLATFORM_PERMISSIONS = (
    PermissionDef("platform:user:view", "查看用户"),
    PermissionDef("platform:user:manage", "管理用户"),
    PermissionDef("platform:role:view", "查看角色"),
    PermissionDef("platform:role:manage", "管理角色"),
)

PLATFORM_MENUS = (
    MenuDef("用户管理", "/platform/users", icon="user", order=10, permission="platform:user:view"),
    MenuDef("角色管理", "/platform/roles", icon="role", order=20, permission="platform:role:view"),
)
