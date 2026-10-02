"""模块契约校验：不合规的模块必须在启动时就失败，而不是留到运行期。"""

import importlib

import pytest

from platforms.contract import MenuDef, ModuleSpec, PermissionDef
from platforms.gateway.loader import (
    ModuleLoadError,
    _topo_sort,
    load_modules,
    validate_spec,
)


def _spec(**kwargs) -> ModuleSpec:
    return ModuleSpec(**{"name": "demo", "title": "示例", **kwargs})


def test_accepts_conforming_spec():
    validate_spec(
        _spec(
            permissions=(PermissionDef("demo:item:view", "查看"),),
            menus=(MenuDef("条目", "/demo/items", permission="demo:item:view"),),
        ),
        "demo",
    )


def test_rejects_name_mismatch():
    with pytest.raises(ModuleLoadError, match="须与目录名一致"):
        validate_spec(_spec(name="other"), "demo")


def test_rejects_invalid_module_name():
    with pytest.raises(ModuleLoadError, match="不合规"):
        validate_spec(_spec(name="Demo-1"), "Demo-1")


def test_rejects_permission_without_module_prefix():
    with pytest.raises(ModuleLoadError, match="开头"):
        validate_spec(_spec(permissions=(PermissionDef("other:item:view", "查看"),)), "demo")


def test_rejects_permission_with_wrong_shape():
    with pytest.raises(ModuleLoadError, match="格式"):
        validate_spec(_spec(permissions=(PermissionDef("demo:item", "查看"),)), "demo")


def test_rejects_menu_outside_module_path():
    with pytest.raises(ModuleLoadError, match="菜单路径"):
        validate_spec(_spec(menus=(MenuDef("条目", "/other/items"),)), "demo")


def test_rejects_menu_referencing_undeclared_permission():
    with pytest.raises(ModuleLoadError, match="未声明的权限码"):
        validate_spec(_spec(menus=(MenuDef("条目", "/demo/items", permission="demo:item:view"),)), "demo")


def test_rejects_menu_with_missing_parent():
    with pytest.raises(ModuleLoadError, match="父菜单"):
        validate_spec(_spec(menus=(MenuDef("条目", "/demo/items", parent="/demo/root"),)), "demo")


def test_detects_dependency_cycle():
    specs = {
        "a": _spec(name="a", depends_on=("b",)),
        "b": _spec(name="b", depends_on=("a",)),
    }
    with pytest.raises(ModuleLoadError, match="成环"):
        _topo_sort({"a", "b"}, specs)


def test_dependency_comes_first():
    specs = {
        "a": _spec(name="a", depends_on=("b",)),
        "b": _spec(name="b"),
        "c": _spec(name="c"),
    }
    assert [s.name for s in _topo_sort({"a", "b", "c"}, specs)] == ["b", "a", "c"]


def test_rejects_unknown_enabled_module():
    with pytest.raises(ModuleLoadError, match="不存在"):
        load_modules(["not_exist"])


def test_loads_real_modules():
    assert [spec.name for spec in load_modules([])] == ["example"]


def test_disabled_module_is_not_imported(tmp_path, monkeypatch):
    package = "isolated_modules"
    package_dir = tmp_path / package
    chosen_dir = package_dir / "chosen"
    disabled_dir = package_dir / "disabled"
    chosen_dir.mkdir(parents=True)
    disabled_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (chosen_dir / "module.py").write_text(
        "from platforms.contract import ModuleSpec\nMODULE = ModuleSpec(name='chosen', title='Chosen')\n",
        encoding="utf-8",
    )
    (disabled_dir / "module.py").write_text("raise RuntimeError('disabled module imported')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    assert [spec.name for spec in load_modules(["chosen"], package)] == ["chosen"]
