"""架构边界测试：让"不许跨模块引用"从口头约定变成会失败的用例。

这些规则一旦放松，模块化就只剩目录结构了，所以这里的断言不要加豁免。
"""

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

from platforms.db import PLATFORM_SCHEMA, Base, module_schema
from platforms.gateway.loader import discover_module_names

SERVER = Path(__file__).resolve().parents[2]


def _import_targets(path: Path) -> list[str]:
    """返回文件里所有 import 的完整目标路径，相对导入（模块内部）不参与判断。"""
    targets: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            targets += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            targets += [f"{node.module}.{alias.name}" for alias in node.names]
    return targets


def test_platform_does_not_depend_on_modules():
    """平台层反向依赖业务模块，是模块化崩塌的第一步。"""
    offenders = [
        (path.relative_to(SERVER).as_posix(), target)
        for path in (SERVER / "platforms").rglob("*.py")
        for target in _import_targets(path)
        if target == "modules" or target.startswith("modules.")
    ]
    assert not offenders, f"平台层不得依赖业务模块：{offenders}"


def test_modules_only_import_each_other_contract():
    """模块之间只能通过 contract.py 通信，碰对方的 service/models 一律不允许。"""
    offenders = []
    for name in discover_module_names():
        for path in (SERVER / "modules" / name).rglob("*.py"):
            for target in _import_targets(path):
                other = target.split(".")[1] if target.startswith("modules.") else None
                if other in (None, name):
                    continue
                if not target.startswith(f"modules.{other}.contract"):
                    offenders.append((path.relative_to(SERVER).as_posix(), target))
    assert not offenders, f"跨模块只能 import <模块>.contract：{offenders}"


def test_every_table_lives_in_its_own_schema():
    """平台表在 platform schema，模块表在 mod_<模块名> schema，不允许落到 public。"""
    importlib.import_module("platforms.auth.models")
    allowed = {PLATFORM_SCHEMA}
    for name in discover_module_names():
        if importlib.util.find_spec(f"modules.{name}.models"):
            importlib.import_module(f"modules.{name}.models")
            allowed.add(module_schema(name))

    misplaced = {table.name: table.schema for table in Base.metadata.tables.values() if table.schema not in allowed}
    assert not misplaced, f"这些表没有归属到正确的 schema：{misplaced}"


@pytest.mark.parametrize("name", discover_module_names())
def test_module_exposes_contract(name: str):
    """每个模块都必须有 contract.py，哪怕暂时不对外提供任何能力。"""
    assert (SERVER / "modules" / name / "contract.py").exists(), f"模块 {name} 缺少 contract.py"
