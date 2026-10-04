# 仓库工程规则

规范唯一来源是 [docs/架构规范.md](docs/架构规范.md)，本文件只是其摘要，冲突时以架构规范为准。`docs/*.html` 是设计背景说明，不作为编码约束。修改架构规则时只更新 `docs/架构规范.md`，不要在本文件或各工具配置中另写一份。

涉及模块边界、权限、事件、schema 或迁移的改动，先阅读架构规范的对应章节。

## 硬性约束

- 模块名一经确定，后端包、前端目录、接口前缀、路由、schema、权限码、配置前缀、迁移分支都由它推导；显示名与技术模块名分开（§2）。
- 依赖只能 `modules → platforms`，平台层不 import 业务模块；跨模块只能 import 对方的 `contract.py`，返回冻结 DTO（§3）。
- 前端模块不得引用 shell 或其他模块（§3）。
- 模块只读写自己的 schema，禁止跨 schema 的 JOIN、外键和原生 SQL；唯一例外是引用 `platform.user.id`（§3、§4）。
- 事件只用于通知已发生的事实，payload 不含 ORM 对象（§3）。
- 模块名不得占用 `auth`、`admin`、`modules` 等平台保留前缀；权限点只在后端 `module.py` 声明（§4）。
- `scripts/sync_permissions.py` 会删除代码中已移除的权限并级联删除角色授权，运行前确认 `ENABLED_MODULES` 范围（§4、§5）。
- 表结构变更：改所属模块的模型，在该模块的 Alembic 分支用 `--rev-id` 生成四位编号草稿并逐条审阅；`down_revision` 指向分支当前 head，已应用到共享环境的 revision 不得修改（§5）。
- 改名、数据回填、新增非空列、约束变更和破坏性操作需要手写或修正迁移，并在交付时显式说明（§5）。
- 不手工修改生产库；`downgrade` 不作常规回滚，优先向前修复（§5）。

## 改完必须运行

- 后端：`cd server && pytest`（含架构测试）。
- 迁移：`python -m alembic -n <分支> upgrade head` 与 `python -m alembic -n <分支> check`。pytest 夹具用 ORM `create_all`，不会执行迁移文件。
- 前端：`cd web && npm run lint && npm run typecheck`。

优先运行与改动最相关的最小范围测试；无法运行的验证要在结果中说明。

## 变更纪律

- 先阅读现有代码和未提交改动，改动范围最小化，不回滚无关修改。
- 沿用仓库已有模式，测试加在所属模块的边界内。
