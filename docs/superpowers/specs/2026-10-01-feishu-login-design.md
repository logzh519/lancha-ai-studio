# 飞书登录接入设计

日期：2026-10-01
状态：已确认，待实施

## 背景与目标

`lancha-ai-studio` 目前只做授权（RBAC），不做认证。`platforms/auth/principal.py` 的默认实现从 `X-User-Id`
请求头取用户，仅供本地开发；`架构规范.md` 第 4 节明确要求生产环境必须调 `set_principal_provider()`
换成真实实现，第 9 节把「认证与登录」列为当前刻意不做的事。

本次工作就是补上这块留空：接入飞书扫码登录，并把登录打通到可用状态——新人登录后由管理员在界面上
建角色、分配角色，菜单随之生效。

参考实现是 `advertising-center-main`（Go），它已有一套经过生产验证的飞书 OAuth 链路。本设计移植其
流程与安全要点，不移植其角色模型。

## 范围

做：

- 飞书 OAuth 授权码登录，服务端会话
- 外部身份到 `platform.user` 的映射
- 登录页（深色 + Canvas 粒子动画，移植自 `advertising-center`）
- 用户管理页：启用/停用、分配角色
- 角色管理页：建角色、编辑权限码、删除

不做：

- 多 provider 注册表与动态路由（理由见下）
- 诊断模式（飞书原始返回展示）
- 会话设备信息、心跳、在线状态、强制下线
- 邮箱变更历史与冲突裁决
- 数据权限（与本次无关，框架另有规划）

## 关键决策

### 放平台层，但内部切开登录方式

飞书登录代码放 `server/platforms/auth/`，不做成业务模块。原因是架构铁律「平台层永远不 import 业务模块」，
而 `set_principal_provider()` 必须由平台的启动流程调用。

平台层内部按「是否与登录方式相关」切开：

| 文件 | 职责 | 换登录方式时 |
|---|---|---|
| `session.py` | 会话签发、校验、销毁 | 不动 |
| `identity.py` | 外部身份映射到 `user`、首次登录开通 | 不动 |
| `feishu/client.py` | 授权 URL、code 换 token、拉 user_info | 整个替换 |

身份表带 `provider` 字段，以后接公司自有账号系统直接插新行，表结构不动。

**现在不建多 provider 注册表和动态路由**。公司账号系统的接入形态未知，可能是 OIDC、LDAP，也可能是
前置网关透传 JWT，那样连「跳转授权页 → 回调换 token」都不存在。照着飞书的形状定义通用 provider 接口，
真接的时候大概率要重写抽象。等有两个真实实现时再提取。

### 服务端会话，不用 JWT

会话落 `platform.user_session` 表，token 只存 sha256，原值通过 HttpOnly cookie 下发。

`require()` 每个请求本来就要查一次权限码，会话查询与之合并后几乎不增加往返，换来可立即吊销、
改角色立即生效。

### 新用户自动创建但不授予任何角色

首次登录自动建 `user`，不给角色，登录后菜单为空，等管理员在界面上授权。

**不做「首个登录者自动成为超管」**。超管一律按现有 README 的方式手工 SQL 指定。

### `username` 取企业邮箱

身份识别按以下顺序：

1. 按 `(provider='feishu', external_id=open_id)` 查 `user_identity` —— 命中即老用户
2. 未命中，按 `username = 企业邮箱` 查 `user` —— 命中则把飞书身份绑定到该账号
3. 仍未命中，新建 `user`，`username` 取企业邮箱（飞书未返回邮箱时回退 `feishu_{open_id}`）

第 2 步是为以后接公司账号系统预留：同一个人用邮箱能自然合并到同一个 `user`，不会变成两个账号。
这是选邮箱而非 `open_id` 作 `username` 的主要理由——`open_id` 更稳定但完全不可读，且换飞书应用
照样会变（那种情况靠 `union_id` 兜）。

邮箱后续变更时只更新 `user_identity.email`，不改 `username`，避免唯一约束冲突和审计断裂。

### `user` 不加字段

头像和邮箱放 `user_identity`，`user` 继续保持「只存身份标识」的定位。

### `auth_mode` 显式配置

新增配置项 `auth_mode`，取值 `dev_header`（默认）或 `feishu`，由 `create_app()` 据此调
`set_principal_provider()`。

做成显式而不是「配了 `FEISHU_APP_ID` 就自动启用」，是为了避免漏配时静默退回无认证状态——那种故障
在生产上没人会发现。默认值 `dev_header` 保证现有开发流程和全部测试不受影响。

## 数据模型

三张新表，全部建在 `platform` schema，走 `alembic -n platform` 分支。

```sql
platform.user_identity (
  id           BIGSERIAL PRIMARY KEY,
   user_id      BIGINT NOT NULL REFERENCES platform."user"(id) ON DELETE CASCADE,
  provider     VARCHAR(32)  NOT NULL,       -- 'feishu'
  external_id  VARCHAR(128) NOT NULL,       -- 飞书 open_id
  union_id     VARCHAR(128) NOT NULL DEFAULT '',
  email        VARCHAR(255) NOT NULL DEFAULT '',
  avatar_url   VARCHAR(512) NOT NULL DEFAULT '',
  last_login_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, external_id)
);
CREATE INDEX ix_platform_user_identity_user_id ON platform.user_identity (user_id);

platform.user_session (
  token_hash   VARCHAR(64) PRIMARY KEY,     -- sha256 hex，原值只存在 cookie
   user_id      BIGINT NOT NULL REFERENCES platform."user"(id) ON DELETE CASCADE,
  expires_at   TIMESTAMPTZ NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_platform_user_session_user_id ON platform.user_session (user_id);
CREATE INDEX ix_platform_user_session_expires_at ON platform.user_session (expires_at);

platform.oauth_state (
  state_hash   VARCHAR(64) PRIMARY KEY,     -- sha256 hex
  expires_at   TIMESTAMPTZ NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_platform_oauth_state_expires_at ON platform.oauth_state (expires_at);
```

带 schema 的表，SQLAlchemy 生成的索引名带 schema 前缀，手写迁移时必须对齐，否则 `alembic check`
一直有 diff。

## 登录流程

```
未登录访问任意页
  → 路由守卫 GET /api/auth/me → 401 → 跳 /login

/login 点「飞书登录」
  → POST /api/auth/feishu/login-url
     生成 state，sha256 存 oauth_state（10 分钟），返回 authorizeUrl
  → window.location.href = authorizeUrl

飞书授权完成，浏览器回到 GET /api/auth/feishu/callback?code&state
  → DELETE FROM platform.oauth_state
     WHERE state_hash = :h AND expires_at > now() RETURNING state_hash   -- 原子消费
     消费失败 → 302 /login?error=...
  → code 换 user_access_token
     先 POST https://accounts.feishu.cn/oauth/v3/token
     失败回退 POST https://open.feishu.cn/open-apis/authen/v2/oauth/token
  → GET https://open.feishu.cn/open-apis/authen/v1/user_info
  → identity.upsert()，单事务，按「关键决策」的三步规则
  → session.issue()：token 存 sha256，原值写 Set-Cookie
     HttpOnly; SameSite=Lax; Path=/; Secure 由 cookie_secure 控制
  → 302 回前端首页
```

任何一步失败都 302 到 `/login?error=<中文原因>`，不返回 JSON——因为这个地址是浏览器直接访问的。

每请求鉴权由 `session_principal_provider` 完成：读 cookie → sha256 → 一条 SQL join `user_session`
和 `user`（同时校验会话未过期、用户 `is_active`）→ 返回 `Principal`，查不到返回 `ANONYMOUS`。
该 provider 顺带把 `is_superuser` 填进 `Principal`，使 `service.is_superuser()` 短路，省一次查询。

## 回调地址

`vite.config.ts` 的 `/api` 代理设了 `changeOrigin: true`，会把 Host 改写成 target，所以后端不能从
请求头推导回调地址，必须用配置项显式指定。且开发期该值要填**前端**地址：

| 环境 | `FEISHU_REDIRECT_URI` |
|---|---|
| 开发 | `http://localhost:5173/api/auth/feishu/callback` |
| 生产 | `https://<域名>/api/auth/feishu/callback` |

飞书会把浏览器直接重定向到这个地址。若填 `127.0.0.1:8000`，cookie 落在 8000 域下，而前端页面在
5173 域，带不过去，表现为「回调成功但仍然未登录」。填前端地址则经 Vite 代理转发，cookie 落在 5173 域。

生产部署为 nginx 同源反代，不存在该问题。

## 接口清单

认证：

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/auth/config` | 匿名 | 飞书是否已配置 |
| POST | `/api/auth/feishu/login-url` | 匿名 | 生成 state 与授权 URL |
| GET | `/api/auth/feishu/callback` | 匿名 | 飞书回调，建会话后 302 |
| GET | `/api/auth/me` | 登录 | 当前用户资料 |
| POST | `/api/auth/logout` | 登录 | 删会话、清 cookie |

用户与角色：

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/api/admin/users` | `platform:user:view` |
| PATCH | `/api/admin/users/{id}/roles` | `platform:user:manage` |
| PATCH | `/api/admin/users/{id}/active` | `platform:user:manage` |
| GET | `/api/admin/roles` | `platform:role:view` |
| POST | `/api/admin/roles` | `platform:role:manage` |
| PATCH | `/api/admin/roles/{id}` | `platform:role:manage` |
| DELETE | `/api/admin/roles/{id}` | `platform:role:manage` |
| GET | `/api/admin/permissions` | `platform:role:view` |

用户列表展示头像、姓名、邮箱、角色、状态、最后登录时间（取 `user_identity.last_login_at`）。
一次返回全部用户，不分页——公司内部系统量级有限，分页等真的慢了再加。不做删除用户和编辑资料，
资料来自飞书，本地改了下次登录会被覆盖。防自锁规则：不允许停用自己。

角色编辑时权限码按 `permission.module` 字段分组展示勾选框。删除角色时 `role_permission` 与
`user_role` 由已有外键 `ON DELETE CASCADE` 自动清理。

## 对现有框架的改动

四处，其中前三处是纯加法：

1. **平台权限码**。新增 `platforms/auth/permissions.py` 声明四个权限码
   （`platform:user:view`、`platform:user:manage`、`platform:role:view`、`platform:role:manage`），
   并让 `registry.all_permissions()` 把它们并入返回值。不改的话 `sync_permissions()` 会把平台权限
   当成「模块里已删除的权限点」清理掉——该函数会 `DELETE` 所有不在声明列表里的权限点。
2. **平台菜单**。`GET /api/modules` 的响应加 `platform_menus` 字段，结构与模块菜单的
   `MenuDef` 一致（`title` / `path` / `icon` / `order` / `permission` / `parent`），同样按当前用户的
   权限码过滤。`AppLayout` 将其渲染成固定的「系统管理」分组，置于模块菜单之后。菜单依然只有后端
   一个来源，不在前端硬编码第二份。
3. **保留模块名**。`loader.py` 增加校验，禁止业务模块取名 `platform`，否则模块权限码会与平台权限码
   撞进同一命名空间。
4. **`PrincipalProvider` 签名加一个参数**，从 `(Request) -> Principal` 改为
   `(Request, AsyncSession) -> Principal`，`current_principal` 相应改为依赖 `get_session`。
   必须这么做：会话 provider 要查库，若让它自建连接，就绕开了 FastAPI 的依赖体系——测试里
   `app.dependency_overrides[get_session]` 将对它失效，provider 读的是真实库而非测试事务，
   登录态在用例中永远读不出来。现有的 `_dev_header_provider` 忽略新参数，行为不变。

另外在 `principal.py` 补一个 `reset_principal_provider()`，供测试在用例之间还原全局 provider——
`create_app()` 在 `auth_mode=feishu` 下会改全局状态，不还原会污染后续用例。

## 配置项

`platforms/config.py` 的 `Settings` 新增：

| 配置 | 默认值 | 说明 |
|---|---|---|
| `auth_mode` | `dev_header` | `dev_header` 或 `feishu` |
| `feishu_app_id` | 空 | |
| `feishu_app_secret` | 空 | |
| `feishu_redirect_uri` | 空 | 见「回调地址」 |
| `feishu_scope` | `auth:user.id:read contact:user.employee:readonly` | 与 `advertising-center` 一致，少一个都拿不全 `open_id` 与企业邮箱 |
| `session_ttl_days` | `7` | |
| `cookie_secure` | `false` | 生产置 `true` |
| `frontend_base_url` | `http://localhost:5173` | 回调成功后的跳转目标 |

`auth_mode=feishu` 但 `feishu_app_id` / `feishu_app_secret` / `feishu_redirect_uri` 任一为空时，
`create_app()` 直接抛错终止启动，不允许带着残缺配置跑起来。

新增依赖 `httpx`（后端当前没有 HTTP 客户端）。

## 前端改动

| 文件 | 改动 |
|---|---|
| `shared/core/request.ts` | 加 `credentials: 'include'`；`VITE_DEV_USER_ID` 仅在 dev_header 模式下发送 |
| `shared/core/session.ts` | 新增 `useSessionStore`：当前用户、`load()`、`logout()` |
| `shell/router.ts` | 新增 `/login` 路由（不套 `AppLayout`）；守卫先取会话，401 跳登录页并带上原路径 |
| `shell/views/LoginView.vue` | 深色登录页，左文案右卡片；读 `?error=` 展示回调失败原因 |
| `shell/components/ParticleField.vue` | Canvas 粒子动画，从 React 版移植，生命周期改 `onMounted` / `onBeforeUnmount` |
| `shell/views/UsersView.vue` | 用户管理页 |
| `shell/views/RolesView.vue` | 角色管理页 |
| `shell/layout/AppLayout.vue` | 右上角用户区（头像、姓名、登出）；渲染平台菜单分组 |
| `shared/ui/styles.css` | 补登录页所需深色 token |

粒子动画是纯 Canvas 逻辑（约 110 行），不依赖 React，移植为机械工作。

## 测试

自动化：

- 会话签发、过期、登出
- state 重放与过期被拒
- 身份映射三条分支：命中已有身份 / 按邮箱合并到已有账号 / 新建账号
- 用户与角色接口的权限校验，以及不允许停用自己
- 飞书 HTTP 调用用 `httpx` 的 mock transport，不打真实网络

现有 `tests/platforms/test_architecture.py` 的 AST 边界扫描自动覆盖新增代码。

## 验收标准

1. `alembic -n platform upgrade head` 后三张新表存在，`alembic -n platform check` 无 diff
2. `AUTH_MODE=dev_header`（默认）时 `pytest` 全绿，行为与改动前完全一致
3. `AUTH_MODE=feishu` 时未登录访问任意页跳 `/login`，登录后跳回原路径
4. 真实飞书扫码能进首页，右上角显示飞书姓名和头像
5. 新用户登录后菜单为空；超管建角色、勾权限、分配给他，刷新后对应菜单出现
6. 登出后 cookie 清除，再访问跳回 `/login`
7. 同一个 `state` 第二次回调被拒绝；超过 10 分钟的 `state` 被拒绝
