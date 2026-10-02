"""扫描模块目录，导入各模块的 module.py 取出 MODULE，校验命名规范并按依赖排序。

这里的校验是"规范可强制"的第一道关：命名写错、权限码前缀不对、菜单路径越界、依赖成环，
都在进程启动时直接失败，而不是等到运行期才发现。
"""

import importlib
import re
from pathlib import Path

from platforms.auth.permissions import PLATFORM_MODULE_NAME
from platforms.contract import ModuleSpec

MODULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ModuleLoadError(Exception):
    """模块不符合契约，或依赖关系有问题。"""


def discover_module_names(package: str = "modules") -> list[str]:
    """返回包目录下所有含 module.py 的子目录名（按名称排序）。"""
    pkg = importlib.import_module(package)
    names = {p.parent.name for base in pkg.__path__ for p in Path(base).glob("*/module.py")}
    return sorted(names)


def _import_spec(name: str, package: str) -> ModuleSpec:
    spec = getattr(importlib.import_module(f"{package}.{name}.module"), "MODULE", None)
    if not isinstance(spec, ModuleSpec):
        raise ModuleLoadError(f"{package}/{name}/module.py 必须导出 MODULE = ModuleSpec(...)")
    return spec


def validate_spec(spec: ModuleSpec, directory: str) -> None:
    """校验模块声明是否符合命名规范。"""
    if spec.name == PLATFORM_MODULE_NAME:
        raise ModuleLoadError(f"模块名 {PLATFORM_MODULE_NAME!r} 为平台保留，会与平台权限码撞进同一命名空间")
    if spec.name != directory:
        raise ModuleLoadError(f"模块 {directory} 的 MODULE.name 为 {spec.name!r}，须与目录名一致")
    if not MODULE_NAME_PATTERN.match(spec.name):
        raise ModuleLoadError(f"模块名 {spec.name!r} 不合规：只允许小写字母、数字、下划线，且以字母开头")

    declared = {p.code for p in spec.permissions}
    for permission in spec.permissions:
        if not permission.code.startswith(f"{spec.name}:"):
            raise ModuleLoadError(f"权限码 {permission.code!r} 须以 {spec.name}: 开头")
        if permission.code.count(":") != 2:
            raise ModuleLoadError(f"权限码 {permission.code!r} 格式须为 <模块名>:<资源>:<动作>")
    if len(declared) != len(spec.permissions):
        raise ModuleLoadError(f"模块 {spec.name} 存在重复的权限码")

    paths = {menu.path for menu in spec.menus}
    for menu in spec.menus:
        if menu.path != f"/{spec.name}" and not menu.path.startswith(f"/{spec.name}/"):
            raise ModuleLoadError(f"菜单路径 {menu.path!r} 须以 /{spec.name} 开头")
        if menu.permission is not None and menu.permission not in declared:
            raise ModuleLoadError(f"菜单 {menu.path!r} 引用了未声明的权限码 {menu.permission!r}")
        if menu.parent is not None and menu.parent not in paths:
            raise ModuleLoadError(f"菜单 {menu.path!r} 的父菜单 {menu.parent!r} 不存在")

    for event in spec.subscriptions:
        if "." not in event:
            raise ModuleLoadError(f"事件名 {event!r} 格式须为 <模块名>.<事件>")


def _topo_sort(names: set[str], specs: dict[str, ModuleSpec]) -> list[ModuleSpec]:
    """依赖在前，被依赖方先启动；成环时报出环上的模块。"""
    ordered: list[ModuleSpec] = []
    done: set[str] = set()
    visiting: list[str] = []

    def visit(name: str) -> None:
        if name in done:
            return
        if name in visiting:
            cycle = " -> ".join(visiting[visiting.index(name):] + [name])
            raise ModuleLoadError(f"模块依赖成环：{cycle}")
        visiting.append(name)
        for dep in specs[name].depends_on:
            visit(dep)
        visiting.pop()
        done.add(name)
        ordered.append(specs[name])

    for name in sorted(names):
        visit(name)
    return ordered


def load_modules(enabled: list[str], package: str = "modules") -> list[ModuleSpec]:
    """按 enabled 过滤后导入模块；enabled 为空则加载全部。"""
    available = discover_module_names(package)
    unknown = [name for name in enabled if name not in available]
    if unknown:
        raise ModuleLoadError(f"ENABLED_MODULES 中的模块不存在：{unknown}，可用模块：{available}")

    specs: dict[str, ModuleSpec] = {}
    pending = list(enabled or available)
    while pending:
        name = pending.pop()
        if name in specs:
            continue
        spec = _import_spec(name, package)
        validate_spec(spec, name)
        specs[name] = spec
        for dependency in spec.depends_on:
            if dependency not in available:
                raise ModuleLoadError(f"模块 {name} 依赖的 {dependency} 不存在")
            pending.append(dependency)

    return _topo_sort(set(specs), specs)
