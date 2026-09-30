"""已加载模块的进程内注册表：模块元信息只在 module.py 声明一次，其余地方都从这里读。"""

from platforms.contract import ModuleSpec, PermissionDef

_specs: tuple[ModuleSpec, ...] = ()


def register(specs: list[ModuleSpec]) -> None:
    global _specs
    _specs = tuple(specs)


def loaded_modules() -> tuple[ModuleSpec, ...]:
    return _specs


def all_permissions() -> tuple[PermissionDef, ...]:
    return tuple(permission for spec in _specs for permission in spec.permissions)
