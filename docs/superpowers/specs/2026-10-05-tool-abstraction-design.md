# Tool 抽象与规范设计

日期：2026-10-05
状态：待实现
上游依据：`docs/history/架构设计-V4.0.0.md` §5.3（Tool 定义）、`docs/history/架构设计-V5.0.0.md` §1.1、§4.7

## 背景与目标

商品资产库需要「按 ASIN 自动获取主图副图、生成三视图与三视图参考图」。按 V4 §5.3 的划分，这些都是具体的
Tool。在写任何一个具体 Tool 之前，先把 Tool 这一层的形状、边界和约束定下来，避免每个 Tool 各写一套。

V4 §5.3 已经定义了 Tool，但那份接口是**相对一个尚不存在的 Runner** 写的：`ToolSettings` 里的
`idempotency_key`、`prompt`、`attempt`、`submit_external`、`resume_job_id` 全部由编排引擎提供，而
`node`、`external_call`、`prompt_template` 三张表和 Runner 本身都还没有。其中 `submit_external` /
`resume_job_id` 服务于「Tool 内等待外部作业」，这个前提已被 V5 §4.7 的提交-对账两段式推翻。

因此本次不照抄 V4 接口，而是取其**语义边界**，字段按最小集起步。

## 范围

做：

- `modules/tiktok_studio/tools/` 下的 Tool 基类、`ToolSettings`、`ToolResult`、`ToolError`、`ToolDeps`
- 工厂注册表 `build(name, deps) -> Tool`
- 第一个真实 Tool：`template_match`
- 模块内架构测试：`tools/` 不得 import 本模块的 `api.py` 与 `module.py`
- `docs/架构规范.md` 增加一小节，把 Tool 边界列为强制规则并指向本文

不做：

- 对象存储、HTTP 客户端、LLM 网关、浏览器池等基础设施服务（没有真实来源前不进 `ToolDeps`）
- Runner、`node`、`task`、`channel`、租约、`external_call`（V5 阶段 2）
- `amazon_scrape`、`three_view_gen`、`seedance_generate` 等需要上述基础设施的 Tool
- ASIN 导入链路本身，不改 `product_master`
- 把 Tool 抽象提取到 `platforms/`

## 关键决策

### Tool 放在模块层

V5 §1.1 已有结论：平台层不为本模块新增业务能力，`node` / `channel_config` 这类表不升格为平台通用表，
「等图片生成模块真正要用时再提取，届时已经有两个真实用例可参照」。Tool 抽象同理，放
`modules/tiktok_studio/tools/`。

提取到平台层的触发条件：出现第二个模块需要同样的 Tool 机制。届时迁移的只是基类与注册表，没有数据，成本很低。

### 边界沿用 V4，不放松

| 依赖类型 | 举例 | 是否允许 |
|---|---|---|
| 基础设施服务 | 对象存储、HTTP 客户端、LLM 网关 | 允许，必须构造注入 |
| 业务数据源 | 脚本模板库、商品库、抓取缓存 | 允许，构造注入 |
| 编排状态 | `task`、`node`、`batch`、`review_action` | **禁止** |
| 限流与重试决策 | 「要不要退避」「通道还有名额吗」 | **禁止** |
| 自身位置信息 | 「我是第几个节点」「上游是谁」 | **禁止** |

一句话：**Tool 的边界不是「不碰存储」，而是「不碰编排」。**

### Pydantic 模型，而非手写 JSON Schema

V4 写的是 `input_schema` / `output_schema` 两个 JSON Schema dict。本仓库已经全面用 Pydantic 做校验
（`schemas.py`），再引入一套手写 JSON Schema 等于开第二套校验体系，且 `payload: dict` 在 IDE 和 ruff 下
完全没有类型信息。

改为每个 Tool 声明两个 Pydantic 模型。V4 要的「Runner 据此校验输入」由
`input_model.model_json_schema()` 自动导出，语义不变。

### `run` 与 `execute` 分离

子类实现类型化的 `run(payload: In, settings) -> Out`；调用方用 `execute(payload: dict, settings) -> ToolResult`。

这个分离是为将来的 Runner 准备的：Runner 从管线定义里拿到的只是 `"template_match"` 这个字符串，输入来自
上游节点的 JSON，它不可能持有具体类型。`execute` 负责校验输入、调用 `run`、把结果包成 `ToolResult`；
`run` 里面则是全程有类型的业务代码。

### 字段按最小集起步

`ToolSettings` 与 `ToolResult` **只放现在有真实来源的字段**。V4 的 `external_calls`、`metrics`、`prompt`、
`idempotency_key`、`attempt` 全部不进来，等对应的表和 Runner 存在时再加。

这条是规范的一部分，不只是本次的权宜：**没有真实来源的字段不进契约**。否则 Tool 作者会对着永远是 `None`
的字段写防御逻辑，而那些逻辑从未被执行过，等真正有值时反而是错的。

### 错误语义：业务失败返回，未预期异常抛出

- 业务失败（没匹配到模板、上游返回 4xx、素材不可用）抛 `ToolError(code, message)`，由基类转成
  `success=False` 的 `ToolResult`。
- 输入校验失败返回 `error_code="invalid_input"`，同样是结果而非异常——它是上游数据问题，Runner 应当
  记录为不可重试的失败。
- **其他异常一律不捕获，直接向上抛。**

最后一条是刻意的。把未预期异常也吞成 `ToolResult` 会让真正的 bug 伪装成一次普通的业务失败；等将来接上
自动重试，一个空指针会变成反复重试、反复扣费，且在监控上和正常的业务失败无法区分。

`error_code` 只表达业务语义，**Tool 不判断自己是否该被重试**——retryable 的映射由调用方维护，这是 V4 的
分工。

### 依赖注入：工厂注册表

V4 要求「只注入需要的」，即每个 Tool 的 `__init__` 签名各不相同。但 Runner 需要按字符串统一构造。
两者用一张工厂映射表调和：

```python
_FACTORIES: dict[str, Callable[[ToolDeps], Tool]] = {
    TemplateMatchTool.name: lambda d: TemplateMatchTool(session=d.session),
    # 将来：AmazonScrapeTool.name: lambda d: AmazonScrapeTool(storage=d.storage, http=d.http),
}
```

`ToolDeps` 是「调用方能提供的基础设施全集」，工厂从中挑出每个 Tool 真正需要的。Tool 自身的签名仍然只列
它用得到的依赖，边界由签名保证而不是靠评审。代价是每加一个 Tool 多一行映射。

## 接口定义

```python
# modules/tiktok_studio/tools/base.py

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
    """业务失败。code 供调用方判定是否可重试，Tool 自己不做重试决策。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Tool[In: BaseModel, Out: BaseModel](ABC):
    name: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def run(self, payload: In, settings: ToolSettings) -> Out:
        """业务能力本体。失败抛 ToolError，不返回错误码。"""

    async def execute(self, payload: dict, settings: ToolSettings) -> ToolResult:
        """调用方入口：校验输入 → run → 包成 ToolResult。"""
```

输出不需要单独校验：`run` 的返回值已经是 `Out` 实例，由构造时保证合法，`execute` 只做
`model_dump(mode="json")`。

调用方式：

```python
tool = tools.build("template_match", ToolDeps(session=session))
result = await tool.execute({"category": "top"}, ToolSettings(timeout=10, trace_id=trace_id))
```

## 第一个 Tool：template_match

选它的理由：它是 V4 §5.3.5 清单里的真实 Tool，属 `local` 通道，读的是仓库里已经存在的
`script_template` 表，零新增基础设施，能完整跑通注册表、依赖注入、输入校验、`ToolError` 四条通路。

输入只有类目，输出带上模板全文与标识：

```python
class TemplateMatchInput(BaseModel):
    category: Category          # all | top | bottom


class TemplateMatchOutput(BaseModel):
    template_id: int
    name: str
    category: Category
    duration_seconds: int
    content: str
    version: str
```

匹配规则：

1. 只从 `status = 'formal'` 的模板里选，测试模板不进候选池。
2. 候选池 = 类目为「全品类」的模板 + 类目等于入参的模板。即入参为「上衣」时，全品类和上衣的模板一起参与。
   入参本身为「全品类」时，候选池退化为只有全品类模板。
3. 从候选池里**随机取一条**。
4. 时长不参与筛选，由选中的模板自带，随输出返回。
5. 候选池为空时抛 `ToolError("no_template_matched", ...)`。

随机选取意味着同样的输入可能选出不同模板。这不影响可追溯性——输出里带 `template_id`，「这条视频用了哪个
模板」始终可查；节点重跑换一个模板，恰好符合「重摇」的意图。

实现上用 SQL 的 `ORDER BY random() LIMIT 1`，不把候选集拉到内存。

## 约束的可执行化

仓库的一贯取向是「这些约束是可执行的，不是口头约定」（架构规范 §3）。Tool 规范里最容易被破坏的是「不碰
编排」，因此加一条模块内架构测试：

- `tools/` 下任何文件不得 import 本模块的 `api.py` 与 `module.py`

等 `node`、`task` 模型落地后，这条测试追加禁止 import 编排模型。跨模块 import 已由
`tests/platforms/test_architecture.py` 覆盖，不重复。

测试放 `server/tests/modules/tiktok_studio/`（架构规范要求测试加在所属模块的边界内）。

## 文件清单

```
server/modules/tiktok_studio/tools/
    __init__.py           _FACTORIES 与 build()，并对外导出 base 中的契约类型
    base.py               Tool、ToolSettings、ToolDeps、ToolResult、ToolError
    template_match.py     TemplateMatchTool 与其输入输出模型
server/modules/tiktok_studio/service.py
    新增 pick_script_template()
server/tests/modules/tiktok_studio/
    test_tools.py         基类行为、注册表、template_match 规则、架构约束
docs/架构规范.md          新增 Tool 层小节
```

不涉及表结构变更，没有迁移。

## 与 V4 的差异对照

| V4 原文 | 本设计 | 原因 |
|---|---|---|
| `input_schema` / `output_schema` 为 JSON Schema dict | Pydantic 模型，JSON Schema 自动导出 | 仓库已用 Pydantic，避免第二套校验体系 |
| `execute(payload: dict)` 单一入口 | `run` 类型化 + `execute` dict 入口 | 兼顾 Runner 的字符串调用与实现内的类型安全 |
| `ToolSettings` 含 `idempotency_key`、`prompt`、`attempt` | 暂不含 | 对应的表与 Runner 不存在，无真实来源 |
| `ToolSettings` 含 `submit_external`、`resume_job_id` | 不含 | V5 §4.7 已用提交-对账两段式取代「Tool 内等待」 |
| `ToolResult` 含 `external_calls`、`metrics` | 暂不含 | `external_call` 表不存在 |
| 依赖直接构造注入 | 构造注入 + 工厂映射表 | Runner 需要按名字统一构造 |

## 验收标准

- `cd server && pytest` 全绿，含新增的 `test_tools.py` 与架构约束测试
- `template_match` 能通过注册表按名字构造并执行，返回 `success=True` 与合法输出
- 候选池为空时返回 `success=False` 且 `error_code="no_template_matched"`
- 输入非法时返回 `error_code="invalid_input"`
- `run` 内抛出的非 `ToolError` 异常能穿透 `execute` 向上抛
- ruff 无新增告警
