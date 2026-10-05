# Tool 抽象与规范 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `tiktok_studio` 模块内建立 Tool 层：契约基类、工厂注册表，以及第一个真实 Tool `template_match`。

**Architecture:** Tool 是一项业务能力的完整封装，只碰基础设施与业务数据源，不碰编排状态。子类实现类型化的 `run`，调用方用 dict 进 / `ToolResult` 出的 `execute`，后者是将来 Runner 按字符串调用所需的形状。依赖构造注入，由注册表里的工厂从 `ToolDeps` 中挑出每个 Tool 真正需要的那几样。

**Tech Stack:** Python 3.14.4、Pydantic 2.13.5（PEP 695 泛型语法）、SQLAlchemy 2.1 async、pytest + pytest-asyncio（`asyncio_mode=auto`）。

**Spec:** `docs/superpowers/specs/2026-10-05-tool-abstraction-design.md`

## Global Constraints

- 所有命令在 `server/` 目录、已激活 `.venv`（`source .venv/bin/activate`）下执行。
- 不涉及表结构变更，**不生成任何 Alembic 迁移**。
- 注释、文档字符串、错误信息一律中文，风格与现有代码一致；不写解释「这次改了什么」的注释。
- Tool 边界以 `docs/架构规范.md` §3「模块内的 Tool 层」为准：不读写编排状态，不做限流，瞬时故障可在 Tool 内用 `retry_async` 有限次重试，依赖一律构造注入。
- 契约字段只在有真实来源时新增。`ToolSettings` 本次只有 `timeout`、`trace_id`；`ToolResult` 本次只有 `success`、`output`、`error_code`、`error_message`。不得添加 `idempotency_key`、`prompt`、`attempt`、`external_calls`、`metrics`。
- 业务失败抛 `ToolError`；输入校验失败返回 `error_code="invalid_input"`；**其他异常一律不捕获**。
- `pytest` 的 `asyncio_mode=auto`，异步测试函数不需要 `@pytest.mark.asyncio`。
- 需要数据库的测试加 `@pytest.mark.db`（连不上 PostgreSQL 时自动跳过）。
- 仓库没有 ruff 配置文件，全仓基线 103 条告警，因此门禁只针对新增文件：新增的 5 个文件 `ruff check` 必须零告警。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `server/modules/tiktok_studio/tools/base.py` | 新 | `Tool`、`ToolSettings`、`ToolDeps`、`ToolResult`、`ToolError` |
| `server/modules/tiktok_studio/tools/template_match.py` | 新 | `TemplateMatchTool` 与其输入输出模型 |
| `server/modules/tiktok_studio/tools/__init__.py` | 新 | `_FACTORIES`、`build()`，并对外导出 base 中的契约类型 |
| `server/modules/tiktok_studio/service.py` | 改 | 新增 `pick_script_template()` |
| `server/tests/modules/tiktok_studio/test_tools.py` | 新 | 基类行为（无数据库）与注册表（数据库） |
| `server/tests/modules/tiktok_studio/test_tools_template_match.py` | 新 | `template_match` 匹配规则（数据库） |
| `server/tests/platforms/test_architecture.py` | 改 | 新增「`tools/` 不得 import 本模块 `api` 与 `module`」 |

spec 里列的「`docs/架构规范.md` 增加 Tool 层小节」已随设计文档一起提交（`8b84965`），本计划不再重复。

**与 spec 的一处偏离**：spec 写的是把架构测试放在 `tests/modules/tiktok_studio/`。但 `docs/架构规范.md` 已把 `modules/<模块名>/tools/` 定为全仓约定，而 `tests/platforms/test_architecture.py` 里已有结构完全相同的 `test_only_module_py_imports_own_worker`（遍历所有模块）。因此这条通用规则放进 `test_architecture.py`，与 worker 那条并列。等 `node`、`task` 模型落地后，「不得 import 编排模型」那条再作为模块专属测试放回模块目录。

---

### Task 1: Tool 基类与契约

**Files:**
- Create: `server/modules/tiktok_studio/tools/__init__.py`（本任务只放包说明，注册表在 Task 3 补）
- Create: `server/modules/tiktok_studio/tools/base.py`
- Test: `server/tests/modules/tiktok_studio/test_tools.py`

**Interfaces:**
- Produces:
  - `ToolSettings(timeout: float, trace_id: str)`，frozen dataclass
  - `ToolDeps(session: AsyncSession)`，frozen dataclass
  - `ToolResult(success: bool, output: dict, error_code: str | None = None, error_message: str | None = None)`，frozen dataclass
  - `ToolError(code: str, message: str)`，异常，属性 `.code` / `.message`
  - `Tool[In: BaseModel, Out: BaseModel]`，抽象基类，类属性 `name` / `input_model` / `output_model`，抽象方法 `async run(payload: In, settings: ToolSettings) -> Out`，具体方法 `async execute(payload: dict, settings: ToolSettings) -> ToolResult`

- [ ] **Step 1: 建包目录与包说明**

创建 `server/modules/tiktok_studio/tools/__init__.py`：

```python
"""Tool 层：一项业务能力的完整封装。

边界见 docs/架构规范.md §3「模块内的 Tool 层」。
"""
```

- [ ] **Step 2: 写失败的测试**

创建 `server/tests/modules/tiktok_studio/test_tools.py`：

```python
"""Tool 基类的行为：输入校验、业务失败、未预期异常。"""

import pytest
from pydantic import BaseModel

from modules.tiktok_studio.tools.base import Tool, ToolError, ToolSettings

SETTINGS = ToolSettings(timeout=5.0, trace_id="trace-1")


class EchoInput(BaseModel):
    value: int


class EchoOutput(BaseModel):
    doubled: int


class EchoTool(Tool[EchoInput, EchoOutput]):
    """只在测试里使用的假 Tool，用来驱动基类的四条通路。"""

    name = "echo"
    input_model = EchoInput
    output_model = EchoOutput

    def __init__(self, *, fail_code: str | None = None, crash: bool = False) -> None:
        self._fail_code = fail_code
        self._crash = crash

    async def run(self, payload: EchoInput, settings: ToolSettings) -> EchoOutput:
        if self._crash:
            raise RuntimeError("内部 bug")
        if self._fail_code:
            raise ToolError(self._fail_code, "业务失败")
        return EchoOutput(doubled=payload.value * 2)


async def test_execute_returns_output():
    result = await EchoTool().execute({"value": 3}, SETTINGS)
    assert (result.success, result.output) == (True, {"doubled": 6})
    assert result.error_code is None


async def test_invalid_input_is_a_failed_result_not_an_exception():
    result = await EchoTool().execute({"value": "abc"}, SETTINGS)
    assert (result.success, result.error_code, result.output) == (False, "invalid_input", {})
    assert result.error_message


async def test_tool_error_becomes_failed_result():
    result = await EchoTool(fail_code="no_template_matched").execute({"value": 1}, SETTINGS)
    assert (result.success, result.error_code, result.error_message) == (
        False,
        "no_template_matched",
        "业务失败",
    )


async def test_unexpected_exception_propagates():
    """未预期异常不得被吞成失败结果，否则 bug 会伪装成普通业务失败。"""
    with pytest.raises(RuntimeError, match="内部 bug"):
        await EchoTool(crash=True).execute({"value": 1}, SETTINGS)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd server && source .venv/bin/activate && pytest tests/modules/tiktok_studio/test_tools.py -v`
Expected: 收集阶段就 FAIL，`ModuleNotFoundError: No module named 'modules.tiktok_studio.tools.base'`

- [ ] **Step 4: 实现基类**

创建 `server/modules/tiktok_studio/tools/base.py`：

```python
"""Tool 契约：给它业务参数，它还你可以直接使用的业务结果。

Tool 的边界不是「不碰存储」，而是「不碰编排」：允许访问基础设施服务与业务数据源，
禁止读写任务、节点、批次，禁止判断自己该不该重试。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ToolSettings:
    """调用方注入的运行期参数。Tool 只读，不得据此推断编排逻辑。"""

    timeout: float      # 发起外部调用时由 Tool 自行应用；纯本地 Tool 忽略它
    trace_id: str       # 日志关联用


@dataclass(frozen=True)
class ToolDeps:
    """调用方能提供的基础设施与业务数据源全集。字段只在有真实来源时新增。"""

    session: AsyncSession


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: dict
    error_code: str | None = None
    error_message: str | None = None


class ToolError(Exception):
    """业务失败。Tool 内部重试耗尽后才抛出，code 供调用方判定是否整体重跑。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Tool[In: BaseModel, Out: BaseModel](ABC):
    """依赖一律由子类在 __init__ 中显式声明并构造注入，不在内部读全局配置。"""

    name: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def run(self, payload: In, settings: ToolSettings) -> Out:
        """业务能力本体。失败抛 ToolError，不返回错误码。"""

    async def execute(self, payload: dict, settings: ToolSettings) -> ToolResult:
        """调用方入口：校验输入、调用 run、包成 ToolResult。

        输出不单独校验：run 的返回值已经是 Out 实例，构造时就已合法。
        非 ToolError 的异常不捕获，交给调用方处理。
        """
        try:
            parsed = self.input_model.model_validate(payload)
        except ValidationError as exc:
            return ToolResult(False, {}, "invalid_input", str(exc))
        try:
            output = await self.run(parsed, settings)
        except ToolError as exc:
            return ToolResult(False, {}, exc.code, exc.message)
        return ToolResult(True, output.model_dump(mode="json"))
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd server && source .venv/bin/activate && pytest tests/modules/tiktok_studio/test_tools.py -v`
Expected: 4 passed

- [ ] **Step 6: 检查新文件的 ruff 告警**

Run: `cd server && source .venv/bin/activate && ruff check modules/tiktok_studio/tools tests/modules/tiktok_studio/test_tools.py`
Expected: `All checks passed!`

- [ ] **Step 7: 提交**

```bash
cd /home/lancha/github/lancha-ai-studio
git add server/modules/tiktok_studio/tools server/tests/modules/tiktok_studio/test_tools.py
git commit -m "feat(tiktok_studio): Tool 层契约基类与结果类型"
```

---

### Task 2: template_match 与模板随机匹配查询

**Files:**
- Modify: `server/modules/tiktok_studio/service.py`（在 `delete_script_template` 之后、`list_product_masters` 之前插入）
- Create: `server/modules/tiktok_studio/tools/template_match.py`
- Test: `server/tests/modules/tiktok_studio/test_tools_template_match.py`

**Interfaces:**
- Consumes（Task 1）：`Tool`、`ToolError`、`ToolSettings`
- Produces:
  - `service.pick_script_template(session: AsyncSession, category: str) -> ScriptTemplate | None`
  - `TemplateMatchInput(category: Category)`
  - `TemplateMatchOutput(template_id: int, name: str, category: Category, duration_seconds: int, content: str, version: str)`
  - `TemplateMatchTool(session: AsyncSession)`，类属性 `name = "template_match"`

匹配规则：只取 `status='formal'`；候选池 = 类目为 `all` 的模板 + 类目等于入参的模板；从候选池随机取一条；时长不参与筛选；候选池为空抛 `ToolError("no_template_matched", ...)`。

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/modules/tiktok_studio/test_tools_template_match.py`：

```python
"""template_match 的匹配规则：正式模板、全品类并入候选池、随机取一条。"""

import pytest

from modules.tiktok_studio import service
from modules.tiktok_studio.schemas import ScriptTemplateFields
from modules.tiktok_studio.tools.base import ToolSettings
from modules.tiktok_studio.tools.template_match import TemplateMatchTool

pytestmark = pytest.mark.db

SETTINGS = ToolSettings(timeout=5.0, trace_id="trace-1")
COMMON = {"duration_seconds": 15, "content": "分镜正文", "version": "1.0.0", "reference_video_url": None}


async def _template(session, name: str, category: str, status: str = "formal"):
    fields = ScriptTemplateFields(name=name, category=category, status=status, **COMMON)
    return await service.create_script_template(session, fields, created_by=None)


async def _run(session, category: str):
    return await TemplateMatchTool(session=session).execute({"category": category}, SETTINGS)


async def test_other_categories_are_excluded(session):
    await _template(session, "上衣脚本", "top")
    await _template(session, "下衣脚本", "bottom")

    result = await _run(session, "top")

    assert result.success is True
    assert result.output["name"] == "上衣脚本"


async def test_all_category_templates_join_the_pool(session):
    await _template(session, "通用脚本", "all")

    result = await _run(session, "top")

    assert result.success is True
    assert result.output["name"] == "通用脚本"


async def test_test_status_templates_are_excluded(session):
    await _template(session, "正式脚本", "top")
    await _template(session, "测试脚本", "top", status="test")

    result = await _run(session, "top")

    assert result.output["name"] == "正式脚本"


async def test_empty_pool_returns_tool_error(session):
    await _template(session, "下衣脚本", "bottom")

    result = await _run(session, "top")

    assert (result.success, result.error_code) == (False, "no_template_matched")
    assert result.output == {}


async def test_duration_comes_from_the_matched_template(session):
    fields = ScriptTemplateFields(
        name="长脚本", category="top", status="formal", duration_seconds=60,
        content="分镜正文", version="1.0.0", reference_video_url=None,
    )
    await service.create_script_template(session, fields, created_by=None)

    result = await _run(session, "top")

    assert result.output["duration_seconds"] == 60


async def test_pick_is_random_across_the_pool(session):
    """两条都在候选池里时，多次调用应当都出现过。漏选一条的概率约为 2 × (1/2)^30。"""
    await _template(session, "候选甲", "top")
    await _template(session, "候选乙", "all")

    names = {(await _run(session, "top")).output["name"] for _ in range(30)}

    assert names == {"候选甲", "候选乙"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && source .venv/bin/activate && pytest tests/modules/tiktok_studio/test_tools_template_match.py -v`
Expected: 收集阶段 FAIL，`ModuleNotFoundError: No module named 'modules.tiktok_studio.tools.template_match'`

- [ ] **Step 3: 新增 service 查询**

在 `server/modules/tiktok_studio/service.py` 中，紧跟在 `delete_script_template` 之后插入：

```python
async def pick_script_template(session: AsyncSession, category: str) -> ScriptTemplate | None:
    """从正式模板里随机取一条；候选池 = 全品类模板 + 指定类目的模板。"""
    stmt = (
        select(ScriptTemplate)
        .where(ScriptTemplate.status == "formal", ScriptTemplate.category.in_(("all", category)))
        .order_by(func.random())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()
```

无需改动 import：`select`、`func` 与 `ScriptTemplate` 在该文件中已经引入。

- [ ] **Step 4: 实现 Tool**

创建 `server/modules/tiktok_studio/tools/template_match.py`：

```python
"""按类目从爆款脚本模板库里挑一条正式模板。"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok_studio import service
from modules.tiktok_studio.schemas import Category
from modules.tiktok_studio.tools.base import Tool, ToolError, ToolSettings


class TemplateMatchInput(BaseModel):
    category: Category


class TemplateMatchOutput(BaseModel):
    template_id: int
    name: str
    category: Category
    duration_seconds: int
    content: str
    version: str


class TemplateMatchTool(Tool[TemplateMatchInput, TemplateMatchOutput]):
    """候选池 = 全品类模板 + 入参类目的模板，从中随机取一条。

    随机意味着重跑可能换一条模板；输出带 template_id，用了哪个模板始终可查。
    """

    name = "template_match"
    input_model = TemplateMatchInput
    output_model = TemplateMatchOutput

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def run(self, payload: TemplateMatchInput, settings: ToolSettings) -> TemplateMatchOutput:
        template = await service.pick_script_template(self._session, payload.category)
        if template is None:
            raise ToolError("no_template_matched", f"类目 {payload.category} 下没有可用的正式模板")
        return TemplateMatchOutput(
            template_id=template.id,
            name=template.name,
            category=template.category,
            duration_seconds=template.duration_seconds,
            content=template.content,
            version=template.version,
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd server && source .venv/bin/activate && pytest tests/modules/tiktok_studio/test_tools_template_match.py -v`
Expected: 6 passed

- [ ] **Step 6: 跑一次模块全量测试，确认没碰坏既有用例**

Run: `cd server && source .venv/bin/activate && pytest tests/modules/tiktok_studio -q`
Expected: 全部通过（既有 script_template 与 product_master 用例不受影响）

- [ ] **Step 7: 检查新文件的 ruff 告警**

Run: `cd server && source .venv/bin/activate && ruff check modules/tiktok_studio/tools tests/modules/tiktok_studio/test_tools_template_match.py`
Expected: `All checks passed!`

- [ ] **Step 8: 提交**

```bash
cd /home/lancha/github/lancha-ai-studio
git add server/modules/tiktok_studio/service.py \
        server/modules/tiktok_studio/tools/template_match.py \
        server/tests/modules/tiktok_studio/test_tools_template_match.py
git commit -m "feat(tiktok_studio): template_match tool 与模板随机匹配查询"
```

---

### Task 3: 工厂注册表与 tools 层架构测试

**Files:**
- Modify: `server/modules/tiktok_studio/tools/__init__.py`（替换 Task 1 写入的包说明）
- Modify: `server/tests/modules/tiktok_studio/test_tools.py`（追加注册表用例）
- Modify: `server/tests/platforms/test_architecture.py`（在 `test_only_module_py_imports_own_worker` 之后插入新用例）

**Interfaces:**
- Consumes（Task 1、Task 2）：`Tool`、`ToolDeps`、`ToolError`、`ToolResult`、`ToolSettings`、`TemplateMatchTool`
- Produces:
  - `tools.build(name: str, deps: ToolDeps) -> Tool`，未注册的名字抛 `KeyError`
  - `tools` 包直接导出 `Tool`、`ToolDeps`、`ToolError`、`ToolResult`、`ToolSettings`、`build`

- [ ] **Step 1: 写失败的测试**

先把 `server/tests/modules/tiktok_studio/test_tools.py` 顶部的 import 区改成：

```python
import pytest
from pydantic import BaseModel

from modules.tiktok_studio import tools
from modules.tiktok_studio.tools.base import Tool, ToolError, ToolSettings
from modules.tiktok_studio.tools.template_match import TemplateMatchTool
```

再在文件末尾追加：

```python
@pytest.mark.db
async def test_build_constructs_registered_tool(session):
    tool = tools.build("template_match", tools.ToolDeps(session=session))

    assert isinstance(tool, TemplateMatchTool)
    assert tool.name == "template_match"


@pytest.mark.db
async def test_build_rejects_unknown_name(session):
    with pytest.raises(KeyError, match="未注册的 tool"):
        tools.build("nope", tools.ToolDeps(session=session))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && source .venv/bin/activate && pytest tests/modules/tiktok_studio/test_tools.py -v`
Expected: 新增的两个用例 FAIL，`AttributeError: module 'modules.tiktok_studio.tools' has no attribute 'build'`

- [ ] **Step 3: 实现注册表**

把 `server/modules/tiktok_studio/tools/__init__.py` 整体替换为：

```python
"""Tool 层：一项业务能力的完整封装。

边界见 docs/架构规范.md §3「模块内的 Tool 层」。

调用方按名字构造，不 import 具体 Tool 类：

    tool = tools.build("template_match", tools.ToolDeps(session=session))
    result = await tool.execute({"category": "top"}, ToolSettings(timeout=10, trace_id=trace_id))

新增 Tool 时在 _FACTORIES 里加一行；工厂只挑该 Tool 真正需要的依赖，保证依赖关系写在构造签名上。
"""

from collections.abc import Callable

from modules.tiktok_studio.tools.base import Tool, ToolDeps, ToolError, ToolResult, ToolSettings
from modules.tiktok_studio.tools.template_match import TemplateMatchTool

_FACTORIES: dict[str, Callable[[ToolDeps], Tool]] = {
    TemplateMatchTool.name: lambda deps: TemplateMatchTool(session=deps.session),
}


def build(name: str, deps: ToolDeps) -> Tool:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise KeyError(f"未注册的 tool：{name}，已注册：{sorted(_FACTORIES)}")
    return factory(deps)


__all__ = ["Tool", "ToolDeps", "ToolError", "ToolResult", "ToolSettings", "build"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd server && source .venv/bin/activate && pytest tests/modules/tiktok_studio/test_tools.py -v`
Expected: 6 passed

- [ ] **Step 5: 写失败的架构测试**

在 `server/tests/platforms/test_architecture.py` 中，紧跟 `test_only_module_py_imports_own_worker` 之后插入：

```python
def test_tools_do_not_import_api_or_module():
    """Tool 封装业务能力，不碰编排；引用 api.py 或 module.py 就是把编排拉进了 Tool。"""
    offenders = []
    for name in discover_module_names():
        tools_dir = SERVER / "modules" / name / "tools"
        if not tools_dir.exists():
            continue
        forbidden = (f"modules.{name}.api", f"modules.{name}.module")
        for path in tools_dir.rglob("*.py"):
            for target in _import_targets(path):
                if any(target == item or target.startswith(f"{item}.") for item in forbidden):
                    offenders.append((path.relative_to(SERVER).as_posix(), target))
    assert not offenders, f"tools/ 不得引用本模块的 api 与 module：{offenders}"
```

- [ ] **Step 6: 验证这条测试真的能抓到违规**

先临时在 `server/modules/tiktok_studio/tools/template_match.py` 的 import 区加一行 `from modules.tiktok_studio.api import router  # noqa: F401`，然后运行：

Run: `cd server && source .venv/bin/activate && pytest tests/platforms/test_architecture.py::test_tools_do_not_import_api_or_module -v`
Expected: FAIL，报 `tools/ 不得引用本模块的 api 与 module：[('modules/tiktok_studio/tools/template_match.py', 'modules.tiktok_studio.api.router')]`

删掉这行临时 import 后重新运行：
Expected: PASS

- [ ] **Step 7: 跑全量测试**

Run: `cd server && source .venv/bin/activate && pytest -q`
Expected: 全绿，180 passed（改动前 167，本次新增 13：Task 1 的 4 个、Task 2 的 6 个、Task 3 的 2 个与 1 个架构用例）

- [ ] **Step 8: 检查 ruff**

Run: `cd server && source .venv/bin/activate && ruff check modules/tiktok_studio/tools tests/modules/tiktok_studio/test_tools.py tests/modules/tiktok_studio/test_tools_template_match.py`
Expected: `All checks passed!`

- [ ] **Step 9: 提交**

```bash
cd /home/lancha/github/lancha-ai-studio
git add server/modules/tiktok_studio/tools/__init__.py \
        server/tests/modules/tiktok_studio/test_tools.py \
        server/tests/platforms/test_architecture.py
git commit -m "feat(tiktok_studio): tool 工厂注册表与 tools 层架构约束测试"
```

---

## 完成后的验收

对照 spec 的验收标准逐条确认：

- [ ] `cd server && pytest` 全绿
- [ ] `template_match` 能通过注册表按名字构造并执行，返回 `success=True` 与合法输出（Task 3 Step 1 的 `test_build_constructs_registered_tool` + Task 2 的规则用例）
- [ ] 候选池为空时 `success=False` 且 `error_code="no_template_matched"`（`test_empty_pool_returns_tool_error`）
- [ ] 输入非法时 `error_code="invalid_input"`（`test_invalid_input_is_a_failed_result_not_an_exception`）
- [ ] `run` 内抛出的非 `ToolError` 异常穿透 `execute`（`test_unexpected_exception_propagates`）
- [ ] 新增文件 ruff 零告警
- [ ] 没有生成任何 Alembic 迁移文件
