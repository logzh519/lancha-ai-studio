"""已加载模块的进程内注册表：模块元信息只在 module.py 声明一次，其余地方都从这里读。"""

from platforms.contract import ModuleSpec, PermissionDef

_specs: tuple[ModuleSpec, ...] = ()


def register(specs: list[ModuleSpec]) -> None:
    global _specs
    _specs = tuple(specs)


def loaded_modules() -> tuple[ModuleSpec, ...]:
    return _specs


def all_permissions() -> tuple[PermissionDef, ...]:
    """平台权限码也要进来，否则 sync_permissions 会把它们当成废弃权限删掉。"""
    from platforms.auth.permissions import PLATFORM_PERMISSIONS

    return PLATFORM_PERMISSIONS + tuple(
        permission for spec in _specs for permission in spec.permissions
    )
