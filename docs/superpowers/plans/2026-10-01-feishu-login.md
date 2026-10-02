# 飞书登录接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `lancha-ai-studio` 补上飞书扫码登录与服务端会话，并提供用户/角色管理界面，使 RBAC 从「只能写 SQL」变成「界面可操作」。

**Architecture:** 代码全部落在平台层 `server/platforms/auth/`，内部按「是否与登录方式相关」切开：`session.py` 与 `identity.py` 跟登录方式无关，`feishu/` 是唯一的飞书特有实现。身份表带 `provider` 字段，以后换账号系统只替换 `feishu/`。认证开关由显式配置 `auth_mode` 控制，默认保持现有的 `dev_header` 行为。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2 async / Alembic / httpx / PostgreSQL；前端 Vue 3 `<script setup>` / Pinia / vue-router / Vite。

设计文档：`docs/superpowers/specs/2026-10-01-feishu-login-design.md`

## Global Constraints

- 所有新表建在 `platform` schema，走 `alembic -n platform` 分支；模块表不得被本次改动触碰。
- 带 schema 的表，索引名必须带 schema 前缀（如 `ix_platform_user_identity_user_id`），否则 `alembic -n platform check` 永远有 diff。
- 平台层不得 import `modules.*`，`tests/platforms/test_architecture.py` 会扫 AST 并失败。
- 会话 token、OAuth state 一律只存 sha256 十六进制串，原值只出现在 cookie 或 URL 里。
- `auth_mode` 默认值必须是 `dev_header`，保证现有测试与开发流程零变化。
- `FEISHU_SCOPE` 默认 `auth:user.id:read contact:user.employee:readonly`，少一个就拿不全 `open_id` 与企业邮箱。
- 新文件的 docstring 与注释用中文，解释「为什么」而不是「做了什么」，与现有代码风格一致。
- 测试命令一律在 `server/` 目录下执行；数据库用例标 `@pytest.mark.db`。
- 每个 Task 结束时提交一次，commit message 用 `feat:` / `test:` / `docs:` 前缀。

---

## File Structure

后端新增：

| 文件 | 职责 |
|---|---|
| `server/platforms/auth/models.py`（改） | 追加 `UserIdentity` / `UserSession` / `OAuthState` 三个模型 |
| `server/platforms/migrations/versions/0002_auth_session.py` | 三张表的迁移 |
| `server/platforms/auth/session.py` | 会话签发、解析、销毁，与登录方式无关 |
| `server/platforms/auth/identity.py` | 外部身份映射到 `user`，与登录方式无关 |
| `server/platforms/auth/oauth_state.py` | OAuth state 的创建与原子消费 |
| `server/platforms/auth/feishu/client.py` | 授权 URL、code 换 token、拉 user_info |
| `server/platforms/auth/permissions.py` | 平台自身的权限码与菜单声明 |
| `server/platforms/auth/api.py` | `/api/auth/*` 路由 |
| `server/platforms/auth/admin_api.py` | 用户与角色管理路由 |

后端修改：`config.py`（配置项）、`principal.py`（provider 签名与会话实现）、`gateway/app.py`（装配）、`gateway/api.py`（平台菜单）、`gateway/loader.py`（保留模块名）、`registry.py`（并入平台权限码）、`conftest.py`（还原全局 provider）、`requirements/base.txt`（httpx）。

前端新增：`shared/core/session.ts`、`shell/views/LoginView.vue`、`shell/components/ParticleField.vue`、`shell/views/UsersView.vue`、`shell/views/RolesView.vue`、`shell/api/platform.ts`。
前端修改：`shared/core/request.ts`、`shared/core/types.ts`、`shared/core/index.ts`、`shared/core/platform.ts`、`shell/router.ts`、`shell/layout/AppLayout.vue`。

前端三个任务的切分原则：Task 10 只动数据层，Task 11 建登录页后才接路由，Task 12 建管理页后才接平台路由。
路由永远不引用尚未创建的视图文件，每个任务结束时 `npm run typecheck` 都能过。

---

### Task 1: 数据模型与迁移

**Files:**
- Modify: `server/platforms/auth/models.py`
- Create: `server/platforms/migrations/versions/0002_auth_session.py`
- Test: `server/tests/platforms/test_auth_models.py`

**Interfaces:**
- Consumes: 现有 `platforms.db.Base` / `PLATFORM_SCHEMA`、`platforms.auth.models.TimestampMixin`
- Produces: `UserIdentity`（字段 `id` `user_id` `provider` `external_id` `union_id` `email` `avatar_url` `last_login_at` `created_at` `updated_at`）、`UserSession`（`token_hash` `user_id` `expires_at` `created_at`）、`OAuthState`（`state_hash` `expires_at` `created_at`）

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/platforms/test_auth_models.py`：

```python
"""认证相关表的结构约束：唯一键与级联删除是登录正确性的前提。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from platforms.auth.models import AppUser, OAuthState, UserIdentity, UserSession

pytestmark = pytest.mark.db


async def _user(session, username: str) -> AppUser:
    user = AppUser(username=username, is_superuser=False, is_active=True)
    session.add(user)
    await session.flush()
    return user


async def test_same_provider_external_id_cannot_bind_twice(session):
    first = await _user(session, "identity-a")
    second = await _user(session, "identity-b")
    session.add(UserIdentity(user_id=first.id, provider="feishu", external_id="ou_1"))
    await session.flush()

    session.add(UserIdentity(user_id=second.id, provider="feishu", external_id="ou_1"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_user_removes_identity_and_session(session):
    user = await _user(session, "cascade-target")
    session.add(UserIdentity(user_id=user.id, provider="feishu", external_id="ou_cascade"))
    session.add(
        UserSession(
            token_hash="h" * 64,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    await session.flush()

    await session.delete(user)
    await session.flush()

    assert (await session.execute(select(UserIdentity))).scalars().all() == []
    assert (await session.execute(select(UserSession))).scalars().all() == []


async def test_oauth_state_is_keyed_by_hash(session):
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    session.add(OAuthState(state_hash="s" * 64, expires_at=expires))
    await session.flush()

    session.add(OAuthState(state_hash="s" * 64, expires_at=expires))
    with pytest.raises(IntegrityError):
        await session.flush()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_auth_models.py -v`
Expected: FAIL，`ImportError: cannot import name 'UserIdentity' from 'platforms.auth.models'`

- [ ] **Step 3: 追加三个模型**

在 `server/platforms/auth/models.py` 末尾追加（并把 `DateTime` 之外需要的 `Index` 等补进文件顶部的 import）：

```python
class UserIdentity(TimestampMixin, Base):
    """外部身份到 user 的映射。带 provider 是为了以后接别的账号系统时不用改表结构。"""

    __tablename__ = "user_identity"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_user_identity_provider_external"),
        {"schema": PLATFORM_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(f"{PLATFORM_SCHEMA}.user.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))
    union_id: Mapped[str] = mapped_column(String(128), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    avatar_url: Mapped[str] = mapped_column(String(512), default="")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class UserSession(Base):
    """登录会话。token_hash 是 sha256 十六进制串，原始 token 只存在浏览器 cookie 里。"""

    __tablename__ = "user_session"
    __table_args__ = {"schema": PLATFORM_SCHEMA}

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(f"{PLATFORM_SCHEMA}.user.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthState(Base):
    """OAuth 一次性 state，同样只存哈希，消费时用带有效期条件的 DELETE RETURNING。"""

    __tablename__ = "oauth_state"
    __table_args__ = {"schema": PLATFORM_SCHEMA}

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/test_auth_models.py -v`
Expected: 3 passed

- [ ] **Step 5: 写迁移**

创建 `server/platforms/migrations/versions/0002_auth_session.py`：

```python
"""认证：外部身份、会话与 OAuth state

Revision ID: 0002_auth_session
Revises: 0001_rbac

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_session"
down_revision: Union[str, Sequence[str], None] = "0001_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "platform"


def upgrade() -> None:
    op.create_table(
        "user_identity",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("union_id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("avatar_url", sa.String(length=512), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_user_identity_provider_external"),
        schema=SCHEMA,
    )
    op.create_index("ix_platform_user_identity_user_id", "user_identity", ["user_id"], schema=SCHEMA)

    op.create_table(
        "user_session",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
        schema=SCHEMA,
    )
    op.create_index("ix_platform_user_session_user_id", "user_session", ["user_id"], schema=SCHEMA)
    op.create_index("ix_platform_user_session_expires_at", "user_session", ["expires_at"], schema=SCHEMA)

    op.create_table(
        "oauth_state",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("state_hash"),
        schema=SCHEMA,
    )
    op.create_index("ix_platform_oauth_state_expires_at", "oauth_state", ["expires_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_platform_oauth_state_expires_at", table_name="oauth_state", schema=SCHEMA)
    op.drop_table("oauth_state", schema=SCHEMA)
    op.drop_index("ix_platform_user_session_expires_at", table_name="user_session", schema=SCHEMA)
    op.drop_index("ix_platform_user_session_user_id", table_name="user_session", schema=SCHEMA)
    op.drop_table("user_session", schema=SCHEMA)
    op.drop_index("ix_platform_user_identity_user_id", table_name="user_identity", schema=SCHEMA)
    op.drop_table("user_identity", schema=SCHEMA)
```

- [ ] **Step 6: 验证迁移与模型一致**

Run: `cd server && alembic -n platform upgrade head && alembic -n platform check`
Expected: `No new upgrade operations detected.`

如果报出 diff，九成是索引名没带 `ix_platform_` 前缀，照报错信息对齐即可。

- [ ] **Step 7: 提交**

```bash
git add server/platforms/auth/models.py server/platforms/migrations/versions/0002_auth_session.py server/tests/platforms/test_auth_models.py
git commit -m "feat: 新增外部身份、会话与 OAuth state 三张平台表"
```

---

### Task 2: 会话层

**Files:**
- Create: `server/platforms/auth/session.py`
- Test: `server/tests/platforms/test_auth_session.py`

**Interfaces:**
- Consumes: Task 1 的 `UserSession`；现有 `platforms.auth.principal.Principal`
- Produces:
  - `SESSION_COOKIE: str = "lancha_session"`
  - `hash_token(raw: str) -> str`
  - `async issue(session: AsyncSession, user_id: int, ttl: timedelta) -> str`（返回原始 token）
  - `async resolve(session: AsyncSession, raw_token: str) -> Principal | None`
  - `async revoke(session: AsyncSession, raw_token: str) -> None`

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/platforms/test_auth_session.py`：

```python
"""会话：签发、解析、过期与销毁。原始 token 不得落库。"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from platforms.auth import session as session_module
from platforms.auth.models import AppUser, UserSession

pytestmark = pytest.mark.db


async def _user(session, username: str, *, superuser: bool = False, active: bool = True) -> AppUser:
    user = AppUser(username=username, is_superuser=superuser, is_active=active)
    session.add(user)
    await session.flush()
    return user


async def test_issued_token_is_not_stored_in_plain_text(session):
    user = await _user(session, "session-plain")
    raw = await session_module.issue(session, user.id, timedelta(days=1))

    stored = (await session.execute(select(UserSession))).scalars().one()
    assert stored.token_hash != raw
    assert stored.token_hash == session_module.hash_token(raw)


async def test_resolve_returns_principal_with_superuser_flag(session):
    user = await _user(session, "session-super", superuser=True)
    raw = await session_module.issue(session, user.id, timedelta(days=1))

    principal = await session_module.resolve(session, raw)
    assert principal is not None
    assert principal.user_id == user.id
    assert principal.is_superuser is True


async def test_expired_session_does_not_resolve(session):
    user = await _user(session, "session-expired")
    raw = await session_module.issue(session, user.id, timedelta(seconds=-1))

    assert await session_module.resolve(session, raw) is None


async def test_inactive_user_does_not_resolve(session):
    user = await _user(session, "session-inactive")
    raw = await session_module.issue(session, user.id, timedelta(days=1))
    user.is_active = False
    await session.flush()

    assert await session_module.resolve(session, raw) is None


async def test_revoke_removes_session(session):
    user = await _user(session, "session-revoke")
    raw = await session_module.issue(session, user.id, timedelta(days=1))

    await session_module.revoke(session, raw)

    assert await session_module.resolve(session, raw) is None
    assert (await session.execute(select(UserSession))).scalars().all() == []


async def test_resolve_ignores_empty_token(session):
    assert await session_module.resolve(session, "") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_auth_session.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.auth.session'`

- [ ] **Step 3: 实现会话层**

创建 `server/platforms/auth/session.py`：

```python
"""登录会话：签发、解析、销毁。

这一层与登录方式无关——飞书、公司账号系统或别的任何认证方式，拿到 user_id 之后都走这里。
原始 token 只存在浏览器 cookie 里，库里只有 sha256，库被读走也无法冒充登录。
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth.models import AppUser, UserSession
from platforms.auth.principal import Principal

SESSION_COOKIE = "lancha_session"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def issue(session: AsyncSession, user_id: int, ttl: timedelta) -> str:
    """签发会话并返回原始 token，调用方负责写 cookie。"""
    raw = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            token_hash=hash_token(raw),
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + ttl,
        )
    )
    await session.flush()
    return raw


async def resolve(session: AsyncSession, raw_token: str) -> Principal | None:
    """把 cookie 里的 token 换成 Principal。

    顺手把 is_superuser 带出来，service.is_superuser() 就能短路，不用再查一次库。
    """
    if not raw_token:
        return None
    stmt = (
        select(AppUser.id, AppUser.is_superuser)
        .join(UserSession, UserSession.user_id == AppUser.id)
        .where(
            UserSession.token_hash == hash_token(raw_token),
            UserSession.expires_at > datetime.now(timezone.utc),
            AppUser.is_active.is_(True),
        )
    )
    row = (await session.execute(stmt)).one_or_none()
    return None if row is None else Principal(user_id=row.id, is_superuser=row.is_superuser)


async def revoke(session: AsyncSession, raw_token: str) -> None:
    if not raw_token:
        return
    await session.execute(delete(UserSession).where(UserSession.token_hash == hash_token(raw_token)))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/test_auth_session.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add server/platforms/auth/session.py server/tests/platforms/test_auth_session.py
git commit -m "feat: 会话签发、解析与销毁"
```

---

### Task 3: 身份映射层

**Files:**
- Create: `server/platforms/auth/identity.py`
- Test: `server/tests/platforms/test_auth_identity.py`

**Interfaces:**
- Consumes: Task 1 的 `UserIdentity`；现有 `AppUser`
- Produces:
  - `@dataclass(frozen=True) ExternalProfile`：字段 `provider: str`、`external_id: str`、`union_id: str = ""`、`email: str = ""`、`display_name: str = ""`、`avatar_url: str = ""`
  - `async upsert(session: AsyncSession, profile: ExternalProfile) -> AppUser`

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/platforms/test_auth_identity.py`：

```python
"""身份映射的三条分支：命中已有身份 / 按邮箱合并到已有账号 / 新建账号。"""

import pytest
from sqlalchemy import func, select

from platforms.auth.identity import ExternalProfile, upsert
from platforms.auth.models import AppUser, UserIdentity

pytestmark = pytest.mark.db


def _profile(**overrides) -> ExternalProfile:
    base = {
        "provider": "feishu",
        "external_id": "ou_default",
        "union_id": "on_default",
        "email": "zhang.san@lancha.com",
        "display_name": "张三",
        "avatar_url": "https://example.com/a.png",
    }
    return ExternalProfile(**{**base, **overrides})


async def test_new_user_is_created_without_any_role(session):
    user = await upsert(session, _profile())

    assert user.username == "zhang.san@lancha.com"
    assert user.display_name == "张三"
    assert user.is_superuser is False
    assert user.is_active is True
    identity = (await session.execute(select(UserIdentity))).scalars().one()
    assert identity.user_id == user.id
    assert identity.last_login_at is not None


async def test_second_login_reuses_the_same_user(session):
    first = await upsert(session, _profile())
    second = await upsert(session, _profile(display_name="张三丰"))

    assert first.id == second.id
    assert second.display_name == "张三丰"
    assert (await session.execute(select(func.count()).select_from(AppUser))).scalar_one() == 1


async def test_existing_username_is_merged_instead_of_duplicated(session):
    existing = AppUser(username="li.si@lancha.com", display_name="旧账号", is_superuser=False, is_active=True)
    session.add(existing)
    await session.flush()

    user = await upsert(session, _profile(external_id="ou_lisi", email="li.si@lancha.com"))

    assert user.id == existing.id
    assert (await session.execute(select(func.count()).select_from(AppUser))).scalar_one() == 1


async def test_email_change_updates_identity_but_keeps_username(session):
    user = await upsert(session, _profile())
    changed = await upsert(session, _profile(email="zhang.san@new.com"))

    assert changed.id == user.id
    assert changed.username == "zhang.san@lancha.com"
    identity = (await session.execute(select(UserIdentity))).scalars().one()
    assert identity.email == "zhang.san@new.com"


async def test_missing_email_falls_back_to_external_id(session):
    user = await upsert(session, _profile(email=""))

    assert user.username == "feishu_ou_default"


async def test_email_is_normalised_to_lowercase(session):
    user = await upsert(session, _profile(email="  Zhang.San@Lancha.COM  "))

    assert user.username == "zhang.san@lancha.com"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_auth_identity.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.auth.identity'`

- [ ] **Step 3: 实现身份映射**

创建 `server/platforms/auth/identity.py`：

```python
"""外部身份到 user 的映射。

与登录方式无关：飞书、公司账号系统都把自己的用户资料归一成 ExternalProfile 后交给这里。
认人顺序是「身份 → 邮箱 → 新建」，中间那步是为了同一个人用不同登录方式进来时能合并到一个账号。
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth.models import AppUser, UserIdentity


@dataclass(frozen=True)
class ExternalProfile:
    provider: str
    external_id: str
    union_id: str = ""
    email: str = ""
    display_name: str = ""
    avatar_url: str = ""


def _normalise_email(email: str) -> str:
    return email.strip().lower()


async def upsert(session: AsyncSession, profile: ExternalProfile) -> AppUser:
    """按外部身份找到或创建 user，并刷新身份记录。新用户不授予任何角色。"""
    email = _normalise_email(profile.email)

    identity = (
        await session.execute(
            select(UserIdentity).where(
                UserIdentity.provider == profile.provider,
                UserIdentity.external_id == profile.external_id,
            )
        )
    ).scalar_one_or_none()

    if identity is not None:
        user = await session.get(AppUser, identity.user_id)
    else:
        username = email or f"{profile.provider}_{profile.external_id}"
        user = (
            await session.execute(select(AppUser).where(AppUser.username == username))
        ).scalar_one_or_none()
        if user is None:
            user = AppUser(username=username, display_name=profile.display_name, is_superuser=False, is_active=True)
            session.add(user)
            await session.flush()
        identity = UserIdentity(
            user_id=user.id, provider=profile.provider, external_id=profile.external_id
        )
        session.add(identity)

    # 资料以飞书为准，但 username 一旦确定就不再改——改了会撞唯一约束，也会让审计记录断链。
    if profile.display_name:
        user.display_name = profile.display_name
    identity.union_id = profile.union_id
    identity.email = email
    identity.avatar_url = profile.avatar_url
    identity.last_login_at = datetime.now(timezone.utc)
    await session.flush()
    return user
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/test_auth_identity.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add server/platforms/auth/identity.py server/tests/platforms/test_auth_identity.py
git commit -m "feat: 外部身份到 user 的映射"
```

---

### Task 4: OAuth state

**Files:**
- Create: `server/platforms/auth/oauth_state.py`
- Test: `server/tests/platforms/test_oauth_state.py`

**Interfaces:**
- Consumes: Task 1 的 `OAuthState`；Task 2 的 `hash_token`
- Produces:
  - `async create(session: AsyncSession, ttl: timedelta) -> str`（返回原始 state）
  - `async consume(session: AsyncSession, raw_state: str) -> bool`

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/platforms/test_oauth_state.py`：

```python
"""OAuth state 必须是一次性的，且过期即作废——否则回调可被重放。"""

from datetime import timedelta

import pytest

from platforms.auth import oauth_state

pytestmark = pytest.mark.db


async def test_state_can_be_consumed_once(session):
    raw = await oauth_state.create(session, timedelta(minutes=10))

    assert await oauth_state.consume(session, raw) is True
    assert await oauth_state.consume(session, raw) is False


async def test_expired_state_is_rejected(session):
    raw = await oauth_state.create(session, timedelta(seconds=-1))

    assert await oauth_state.consume(session, raw) is False


async def test_unknown_state_is_rejected(session):
    assert await oauth_state.consume(session, "never-issued") is False


async def test_empty_state_is_rejected(session):
    assert await oauth_state.consume(session, "") is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_oauth_state.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.auth.oauth_state'`

- [ ] **Step 3: 实现 state**

创建 `server/platforms/auth/oauth_state.py`：

```python
"""OAuth 一次性 state。

消费用带有效期条件的 DELETE ... RETURNING，查和删在同一条语句里完成，
并发回调不会出现「两次都通过」的窗口。
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth.models import OAuthState
from platforms.auth.session import hash_token


async def create(session: AsyncSession, ttl: timedelta) -> str:
    raw = secrets.token_urlsafe(24)
    session.add(OAuthState(state_hash=hash_token(raw), expires_at=datetime.now(timezone.utc) + ttl))
    await session.flush()
    return raw


async def consume(session: AsyncSession, raw_state: str) -> bool:
    if not raw_state:
        return False
    stmt = (
        delete(OAuthState)
        .where(
            OAuthState.state_hash == hash_token(raw_state),
            OAuthState.expires_at > datetime.now(timezone.utc),
        )
        .returning(OAuthState.state_hash)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/test_oauth_state.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add server/platforms/auth/oauth_state.py server/tests/platforms/test_oauth_state.py
git commit -m "feat: OAuth 一次性 state 的创建与原子消费"
```

---

### Task 5: 飞书 HTTP 客户端

**Files:**
- Create: `server/platforms/auth/feishu/__init__.py`
- Create: `server/platforms/auth/feishu/client.py`
- Modify: `server/requirements/base.txt`
- Test: `server/tests/platforms/test_feishu_client.py`

**Interfaces:**
- Consumes: Task 3 的 `ExternalProfile`
- Produces: `FeishuClient`（`@dataclass(frozen=True)`，字段 `app_id: str`、`app_secret: str`、`transport: httpx.AsyncBaseTransport | None = None`），方法：
  - `authorize_url(self, redirect_uri: str, state: str, scope: str) -> str`
  - `async exchange(self, code: str, redirect_uri: str) -> str`（返回 user_access_token）
  - `async user_info(self, access_token: str) -> ExternalProfile`
  - 失败时抛 `FeishuError`

- [ ] **Step 1: 加依赖**

在 `server/requirements/base.txt` 的 `python-dotenv` 一行后追加：

```
httpx >= 0.28
```

Run: `cd server && pip install -r requirements/dev.txt`

- [ ] **Step 2: 写失败的测试**

创建 `server/tests/platforms/test_feishu_client.py`：

```python
"""飞书客户端：端点回退、错误识别与资料归一。全部走 mock transport，不打真实网络。"""

import json

import httpx
import pytest

from platforms.auth.feishu.client import FeishuClient, FeishuError

USER_INFO_BODY = {
    "code": 0,
    "msg": "ok",
    "data": {
        "open_id": "ou_1",
        "union_id": "on_1",
        "enterprise_email": "Zhang.San@Lancha.com",
        "name": "张三",
        "en_name": "Zhang San",
        "avatar_url": "https://example.com/a.png",
    },
}


def _client(handler) -> FeishuClient:
    return FeishuClient(app_id="cli_x", app_secret="secret", transport=httpx.MockTransport(handler))


def test_authorize_url_carries_client_id_state_and_scope():
    url = _client(lambda request: httpx.Response(200)).authorize_url(
        "https://app.test/api/auth/feishu/callback", "st4te", "auth:user.id:read"
    )

    assert url.startswith("https://accounts.feishu.cn/open-apis/authen/v1/authorize?")
    assert "client_id=cli_x" in url
    assert "state=st4te" in url
    assert "scope=auth%3Auser.id%3Aread" in url
    assert "response_type=code" in url


async def test_exchange_falls_back_to_legacy_endpoint():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "accounts.feishu.cn" in str(request.url):
            return httpx.Response(500, json={"code": 99, "msg": "boom"})
        return httpx.Response(200, json={"code": 0, "access_token": "u-token"})

    token = await _client(handler).exchange("the-code", "https://app.test/cb")

    assert token == "u-token"
    assert len(seen) == 2
    assert "open.feishu.cn" in seen[1]


async def test_exchange_raises_when_both_endpoints_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20001, "msg": "invalid code"})

    with pytest.raises(FeishuError):
        await _client(handler).exchange("bad-code", "https://app.test/cb")


async def test_user_info_is_normalised_into_external_profile():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer u-token"
        return httpx.Response(200, json=USER_INFO_BODY)

    profile = await _client(handler).user_info("u-token")

    assert profile.provider == "feishu"
    assert profile.external_id == "ou_1"
    assert profile.union_id == "on_1"
    assert profile.email == "Zhang.San@Lancha.com"
    assert profile.display_name == "张三"
    assert profile.avatar_url == "https://example.com/a.png"


async def test_user_info_raises_on_business_error_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"code": 99991663, "msg": "token expired"}))

    with pytest.raises(FeishuError):
        await _client(handler).user_info("stale")


async def test_user_info_without_open_id_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "data": {"name": "张三"}})

    with pytest.raises(FeishuError):
        await _client(handler).user_info("u-token")
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_feishu_client.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.auth.feishu'`

- [ ] **Step 4: 实现客户端**

创建 `server/platforms/auth/feishu/__init__.py`（空文件）与 `server/platforms/auth/feishu/client.py`：

```python
"""飞书 OAuth 客户端。

整个工程里只有这个文件知道飞书的存在，换成别的账号系统时只替换它。
换 token 先打新域名，失败再回退老端点：两套端点在不同租户上的可用性不一致。
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from platforms.auth.identity import ExternalProfile

AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
TOKEN_URLS = (
    "https://accounts.feishu.cn/oauth/v3/token",
    "https://open.feishu.cn/open-apis/authen/v2/oauth/token",
)
USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
TIMEOUT = httpx.Timeout(20.0)


class FeishuError(Exception):
    """飞书接口返回了不可用的结果，调用方据此给用户一句中文提示。"""


@dataclass(frozen=True)
class FeishuClient:
    app_id: str
    app_secret: str
    transport: httpx.AsyncBaseTransport | None = None

    def authorize_url(self, redirect_uri: str, state: str, scope: str) -> str:
        query = {
            "client_id": self.app_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        if scope:
            query["scope"] = scope
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    async def exchange(self, code: str, redirect_uri: str) -> str:
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        last_error = "飞书未返回任何响应"
        async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT) as client:
            for url in TOKEN_URLS:
                try:
                    response = await client.post(url, json=payload)
                    body = response.json()
                except Exception as exc:
                    last_error = f"{url} 请求失败：{exc}"
                    continue
                token = body.get("access_token", "")
                if response.status_code < 300 and body.get("code", 0) == 0 and token:
                    return token
                last_error = f"{url} 返回 status={response.status_code} code={body.get('code')} msg={body.get('msg')}"
        raise FeishuError(f"换取飞书用户 token 失败：{last_error}")

    async def user_info(self, access_token: str) -> ExternalProfile:
        async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT) as client:
            try:
                response = await client.get(USER_INFO_URL, headers={"authorization": f"Bearer {access_token}"})
                body = response.json()
            except Exception as exc:
                raise FeishuError(f"获取飞书用户信息失败：{exc}") from exc
        if response.status_code >= 300 or body.get("code", 0) != 0:
            raise FeishuError(
                f"获取飞书用户信息失败：status={response.status_code} code={body.get('code')} msg={body.get('msg')}"
            )

        data = body.get("data") or {}
        open_id = (data.get("open_id") or "").strip()
        if not open_id:
            raise FeishuError("飞书用户信息缺少 open_id，请检查应用的权限范围配置")
        return ExternalProfile(
            provider="feishu",
            external_id=open_id,
            union_id=(data.get("union_id") or "").strip(),
            email=(data.get("enterprise_email") or "").strip(),
            display_name=(data.get("name") or data.get("en_name") or "").strip(),
            avatar_url=(data.get("avatar_url") or data.get("avatar_thumb") or "").strip(),
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/test_feishu_client.py -v`
Expected: 6 passed

- [ ] **Step 6: 提交**

```bash
git add server/requirements/base.txt server/platforms/auth/feishu/ server/tests/platforms/test_feishu_client.py
git commit -m "feat: 飞书 OAuth HTTP 客户端"
```

---

### Task 6: 配置项与 principal provider 切换

**Files:**
- Modify: `server/platforms/config.py`
- Modify: `server/platforms/auth/principal.py`
- Modify: `server/platforms/gateway/app.py`
- Test: `server/tests/platforms/test_auth_mode.py`

**Interfaces:**
- Consumes: Task 2 的 `session.resolve` / `SESSION_COOKIE`
- Produces:
  - `Settings` 新增 `auth_mode` `feishu_app_id` `feishu_app_secret` `feishu_redirect_uri` `feishu_scope` `session_ttl_days` `cookie_secure` `frontend_base_url`
  - `PrincipalProvider` 签名变为 `Callable[[Request, AsyncSession], Awaitable[Principal]]`
  - `async session_provider(request: Request, session: AsyncSession) -> Principal`
  - `reset_principal_provider() -> None`
  - `create_app()` 在 `auth_mode == "feishu"` 时调 `set_principal_provider(session_provider)`，配置残缺时抛 `RuntimeError`

**为什么要改 provider 签名：** 会话 provider 必须查库。如果让它自己 `AsyncSession(bind=get_engine())`，
就绕开了 FastAPI 依赖体系——测试里 `app.dependency_overrides[get_session]` 对它无效，它读的是真实库
而不是测试事务，刚登录的用户在用例里查不到，`/me` 永远 401。把 session 作为参数传进来即可消除这个裂缝。

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/platforms/test_auth_mode.py`：

```python
"""auth_mode 开关：默认不改变现有行为，开启后配置残缺必须启动即失败。"""

import pytest

from platforms.config import Settings
from platforms.gateway.app import create_app


def test_default_auth_mode_is_dev_header():
    assert Settings().auth_mode == "dev_header"


def test_feishu_mode_requires_full_configuration():
    settings = Settings(auth_mode="feishu", feishu_app_id="cli_x", feishu_app_secret="", feishu_redirect_uri="")
    with pytest.raises(RuntimeError, match="FEISHU"):
        create_app(settings)


def test_feishu_mode_starts_with_full_configuration():
    settings = Settings(
        auth_mode="feishu",
        feishu_app_id="cli_x",
        feishu_app_secret="secret",
        feishu_redirect_uri="https://app.test/api/auth/feishu/callback",
    )
    assert create_app(settings) is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_auth_mode.py -v`
Expected: FAIL，`AttributeError: 'Settings' object has no attribute 'auth_mode'`

- [ ] **Step 3: 加配置项**

在 `server/platforms/config.py` 的 `Settings` 里，`enabled_modules` 之后、PostgreSQL 之前插入：

```python
    # 认证方式：dev_header 用 X-User-Id 请求头（仅限本地开发），feishu 走飞书扫码登录。
    # 做成显式开关而不是「配了 app_id 就自动启用」：漏配时静默退回无认证，在生产上没人会发现。
    auth_mode: str = "dev_header"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    # 飞书会把浏览器直接重定向到这个地址，开发期必须填前端地址（Vite 代理转发），
    # 填后端地址会让 cookie 落在后端域下，前端带不过去。
    feishu_redirect_uri: str = ""
    feishu_scope: str = "auth:user.id:read contact:user.employee:readonly"
    session_ttl_days: int = 7
    cookie_secure: bool = False
    frontend_base_url: str = "http://localhost:5173"
```

- [ ] **Step 4: 改造 principal.py**

把 `server/platforms/auth/principal.py` 从 `PrincipalProvider` 定义起的部分整体替换为：

```python
PrincipalProvider = Callable[[Request, AsyncSession], Awaitable[Principal]]


async def _dev_header_provider(request: Request, session: AsyncSession) -> Principal:
    raw = request.headers.get("X-User-Id")
    if raw is None or not raw.isdigit():
        return ANONYMOUS
    return Principal(user_id=int(raw))


async def session_provider(request: Request, session: AsyncSession) -> Principal:
    """生产实现：从 HttpOnly cookie 读会话。由 create_app() 在 auth_mode=feishu 时装上。

    session 由调用方注入而不是自己建连接——自己建会绕开 FastAPI 的依赖体系，
    测试里对 get_session 的覆盖就对它失效了。
    """
    from platforms.auth.session import SESSION_COOKIE, resolve

    return await resolve(session, request.cookies.get(SESSION_COOKIE, "")) or ANONYMOUS


_provider: PrincipalProvider = _dev_header_provider


def set_principal_provider(provider: PrincipalProvider) -> None:
    global _provider
    _provider = provider


def reset_principal_provider() -> None:
    """还原默认实现。create_app() 会改全局状态，测试用例之间必须还原。"""
    set_principal_provider(_dev_header_provider)


async def current_principal(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Principal:
    """FastAPI 依赖：解析当前主体并挂到 request.state，供日志和后续依赖复用。"""
    principal = await _provider(request, session)
    request.state.principal = principal
    return principal
```

文件顶部的 import 改为：

```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.db import get_session
```

`session_provider` 里的 import 放在函数内，是为了避免 `principal.py` 与 `session.py` 在模块加载期互相牵连。

- [ ] **Step 5: 在 create_app 里装配**

在 `server/platforms/gateway/app.py` 的 `create_app()` 里，`registry.register(modules)` 之后插入：

```python
    if settings.auth_mode == "feishu":
        missing = [
            name
            for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_REDIRECT_URI")
            if not getattr(settings, name.lower())
        ]
        if missing:
            raise RuntimeError(f"AUTH_MODE=feishu 但缺少配置：{'、'.join(missing)}")
        set_principal_provider(session_provider)
```

并在 `app = FastAPI(...)` 之后、挂中间件之前插入：

```python
    # 路由里的 Depends(get_settings) 拿的是 lru_cache 的全局实例，
    # 不接管的话 create_app(settings) 传进来的配置对请求处理完全不生效。
    app.dependency_overrides[get_settings] = lambda: settings
```

文件顶部补 import：

```python
from platforms.auth.principal import session_provider, set_principal_provider
```

`get_settings` 已经在该文件的 import 里，无需重复添加。

- [ ] **Step 6: 加全局状态还原的 fixture**

在 `server/conftest.py` 末尾追加：

```python
@pytest.fixture(autouse=True)
def restore_principal_provider():
    """create_app(auth_mode="feishu") 会全局替换 provider，用例之间必须还原，否则互相污染。"""
    from platforms.auth.principal import reset_principal_provider

    yield
    reset_principal_provider()
```

- [ ] **Step 7: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/test_auth_mode.py tests/platforms/test_gateway.py tests/platforms/test_rbac.py -v`
Expected: 全部 passed（`test_rbac.py` 的 `X-User-Id` 用例必须仍然通过，证明默认行为没变）

- [ ] **Step 8: 提交**

```bash
git add server/platforms/config.py server/platforms/auth/principal.py server/platforms/gateway/app.py server/conftest.py server/tests/platforms/test_auth_mode.py
git commit -m "feat: auth_mode 开关与基于会话的 principal provider"
```

---

### Task 7: 认证路由

**Files:**
- Create: `server/platforms/auth/api.py`
- Modify: `server/platforms/gateway/app.py`
- Test: `server/tests/platforms/test_auth_api.py`

**Interfaces:**
- Consumes: Task 2~6 的全部产出
- Produces: `platforms.auth.api.router`，挂在 `/api/auth`，含
  `GET /config`、`POST /feishu/login-url`、`GET /feishu/callback`、`GET /me`、`POST /logout`；
  以及 `build_feishu_client(settings) -> FeishuClient`（测试通过 `app.dependency_overrides` 替换）

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/platforms/test_auth_api.py`：

```python
"""认证路由：登录链路的端到端行为，含 state 重放与失败跳转。"""

from datetime import timedelta

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from platforms.auth import oauth_state
from platforms.auth.api import build_feishu_client
from platforms.auth.feishu.client import FeishuClient
from platforms.auth.models import AppUser, UserSession
from platforms.auth.session import SESSION_COOKIE, issue
from platforms.config import Settings
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db

SETTINGS = Settings(
    auth_mode="feishu",
    feishu_app_id="cli_x",
    feishu_app_secret="secret",
    feishu_redirect_uri="https://app.test/api/auth/feishu/callback",
    frontend_base_url="https://app.test",
)


def _feishu_handler(request: httpx.Request) -> httpx.Response:
    if "token" in str(request.url):
        return httpx.Response(200, json={"code": 0, "access_token": "u-token"})
    return httpx.Response(
        200,
        json={
            "code": 0,
            "data": {
                "open_id": "ou_1",
                "union_id": "on_1",
                "enterprise_email": "zhang.san@lancha.com",
                "name": "张三",
                "avatar_url": "https://example.com/a.png",
            },
        },
    )


@pytest.fixture
async def client(session):
    app = create_app(SETTINGS)

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[build_feishu_client] = lambda: FeishuClient(
        app_id="cli_x", app_secret="secret", transport=httpx.MockTransport(_feishu_handler)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://app.test") as c:
        yield c


async def test_config_reports_feishu_is_configured(client):
    response = await client.get("/api/auth/config")
    assert response.json() == {"feishu_configured": True}


async def test_login_url_contains_state_and_redirect(client):
    response = await client.post("/api/auth/feishu/login-url")
    url = response.json()["authorize_url"]
    assert url.startswith("https://accounts.feishu.cn/open-apis/authen/v1/authorize?")
    assert "state=" in url


async def test_callback_creates_session_and_redirects_home(client, session):
    raw_state = await oauth_state.create(session, timedelta(minutes=10))

    response = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://app.test/"
    assert response.cookies.get(SESSION_COOKIE)
    user = (await session.execute(select(AppUser))).scalars().one()
    assert user.username == "zhang.san@lancha.com"


async def test_callback_rejects_replayed_state(client, session):
    raw_state = await oauth_state.create(session, timedelta(minutes=10))
    await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    replayed = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert replayed.status_code == 302
    assert replayed.headers["location"].startswith("https://app.test/login?error=")


async def test_callback_with_authorization_error_redirects_to_login(client):
    response = await client.get(
        "/api/auth/feishu/callback",
        params={"error": "access_denied", "state": "whatever"},
        follow_redirects=False,
    )
    assert response.headers["location"].startswith("https://app.test/login?error=")


async def test_callback_refuses_deactivated_user(client, session):
    session.add(AppUser(username="zhang.san@lancha.com", is_superuser=False, is_active=False))
    await session.flush()
    raw_state = await oauth_state.create(session, timedelta(minutes=10))

    response = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert response.headers["location"].startswith("https://app.test/login?error=")
    assert response.cookies.get(SESSION_COOKIE) is None
    assert (await session.execute(select(UserSession))).scalars().all() == []


async def test_me_requires_login(client):
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_me_returns_profile_after_login(client, session):
    raw_state = await oauth_state.create(session, timedelta(minutes=10))
    await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    body = (await client.get("/api/auth/me")).json()

    assert body["username"] == "zhang.san@lancha.com"
    assert body["display_name"] == "张三"
    assert body["avatar_url"] == "https://example.com/a.png"
    assert body["superuser"] is False


async def test_logout_clears_session(client, session):
    raw_state = await oauth_state.create(session, timedelta(minutes=10))
    login = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )
    old_cookie = login.cookies.get(SESSION_COOKIE)

    assert (await client.post("/api/auth/logout")).status_code == 204

    # 响应里的 Set-Cookie 删除会清空 httpx 的 cookie 罐，光看 /me 是 401 证明不了服务端真的撤销了，
    # 所以把旧 token 塞回去再问一次。
    client.cookies.set(SESSION_COOKIE, old_cookie)
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await session.execute(select(UserSession))).scalars().all() == []


async def test_logout_only_revokes_current_device_session(client, session):
    raw_state = await oauth_state.create(session, timedelta(minutes=10))
    await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )
    user = (await session.execute(select(AppUser))).scalars().one()
    other_device_token = await issue(session, user.id, timedelta(days=1))

    await client.post("/api/auth/logout")

    client.cookies.set(SESSION_COOKIE, other_device_token)
    assert (await client.get("/api/auth/me")).status_code == 200
    assert len((await session.execute(select(UserSession))).scalars().all()) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_auth_api.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.auth.api'`

- [ ] **Step 3: 实现路由**

创建 `server/platforms/auth/api.py`：

```python
"""认证路由，挂在 /api/auth 下。

回调是浏览器直接访问的地址，所以成功与失败都用 302 跳回前端，不返回 JSON——
用户看到的应该是登录页上的一句中文，而不是一屏报文。
"""

from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth import identity, oauth_state
from platforms.auth.feishu.client import FeishuClient, FeishuError
from platforms.auth.models import AppUser, UserIdentity
from platforms.auth.principal import Principal, current_principal
from platforms.auth.session import SESSION_COOKIE, issue, revoke
from platforms.config import Settings, get_settings
from platforms.db import get_session

router = APIRouter()

STATE_TTL = timedelta(minutes=10)


def build_feishu_client(settings: Settings = Depends(get_settings)) -> FeishuClient:
    return FeishuClient(app_id=settings.feishu_app_id, app_secret=settings.feishu_app_secret)


@router.get("/config")
async def auth_config(settings: Settings = Depends(get_settings)):
    """前端据此决定登录页上要不要显示飞书按钮。"""
    return {"feishu_configured": bool(settings.feishu_app_id and settings.feishu_redirect_uri)}


@router.post("/feishu/login-url")
async def feishu_login_url(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    feishu: FeishuClient = Depends(build_feishu_client),
):
    state = await oauth_state.create(session, STATE_TTL)
    return {
        "authorize_url": feishu.authorize_url(settings.feishu_redirect_uri, state, settings.feishu_scope),
        "expires_in": int(STATE_TTL.total_seconds()),
    }


@router.get("/feishu/callback")
async def feishu_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    feishu: FeishuClient = Depends(build_feishu_client),
):
    def failed(message: str) -> RedirectResponse:
        return RedirectResponse(f"{settings.frontend_base_url}/login?error={quote(message)}", status_code=302)

    if not await oauth_state.consume(session, state):
        return failed("飞书登录状态无效或已过期，请重新登录。")
    if error:
        return failed("用户取消或拒绝了飞书授权。")
    if not code:
        return failed("飞书回调缺少授权码。")

    try:
        token = await feishu.exchange(code, settings.feishu_redirect_uri)
        profile = await feishu.user_info(token)
    except FeishuError as exc:
        return failed(str(exc))

    user = await identity.upsert(session, profile)
    if not user.is_active:
        # 不拦的话会签发一个永远解析不出身份的 cookie，用户只会被静默弹回登录页，
        # 完全看不出自己是被停用了。
        return failed("账号已被停用，请联系管理员。")
    raw = await issue(session, user.id, timedelta(days=settings.session_ttl_days))

    response = RedirectResponse(f"{settings.frontend_base_url}/", status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me")
async def me(
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    if principal.is_anonymous:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录。")
    stmt = (
        select(AppUser.id, AppUser.username, AppUser.display_name, AppUser.is_superuser, UserIdentity.avatar_url)
        .outerjoin(UserIdentity, UserIdentity.user_id == AppUser.id)
        .where(AppUser.id == principal.user_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录。")
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name,
        "avatar_url": row.avatar_url or "",
        "superuser": row.is_superuser,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    # 只撤销 cookie 对应的那一条会话：在笔记本上点退出，不该把用户手机上的登录也静默踢掉。
    if not principal.is_anonymous:
        await revoke(session, request.cookies.get(SESSION_COOKIE, ""))
    response.delete_cookie(SESSION_COOKIE, path="/")
```

- [ ] **Step 4: 挂载路由**

在 `server/platforms/gateway/app.py` 中，`app.include_router(platform_router, ...)` 之后插入：

```python
    app.include_router(auth_router, prefix="/api/auth", tags=["platform"])
```

顶部补 import：

```python
from platforms.auth.api import router as auth_router
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/test_auth_api.py -v`
Expected: 8 passed

- [ ] **Step 6: 跑一次全量，确认没碰坏既有行为**

Run: `cd server && pytest -q && ruff check .`
Expected: 全部 passed，ruff 无告警

- [ ] **Step 7: 提交**

```bash
git add server/platforms/auth/api.py server/platforms/gateway/app.py server/tests/platforms/test_auth_api.py
git commit -m "feat: 飞书登录、会话下发与登出路由"
```

---

### Task 8: 平台权限码与平台菜单

**Files:**
- Create: `server/platforms/auth/permissions.py`
- Modify: `server/platforms/registry.py`
- Modify: `server/platforms/gateway/api.py`
- Modify: `server/platforms/gateway/loader.py`
- Test: `server/tests/platforms/test_platform_permissions.py`

**Interfaces:**
- Consumes: 现有 `PermissionDef` / `MenuDef`
- Produces:
  - `platforms.auth.permissions.PLATFORM_PERMISSIONS: tuple[PermissionDef, ...]`（四个权限码）
  - `platforms.auth.permissions.PLATFORM_MENUS: tuple[MenuDef, ...]`（两个菜单）
  - `registry.all_permissions()` 返回值包含平台权限码
  - `GET /api/modules` 响应新增 `platform_menus` 字段
  - `loader.load_modules()` 拒绝名为 `platform` 的模块

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/platforms/test_platform_permissions.py`：

```python
"""平台自身的权限码与菜单：必须进同步列表，否则会被 sync_permissions 当成废弃权限清掉。"""

import pytest
from httpx import ASGITransport, AsyncClient

from platforms import registry
from platforms.auth.models import AppUser, Permission, Role, RolePermission, UserRole
from platforms.auth.permissions import PLATFORM_MENUS, PLATFORM_PERMISSIONS
from platforms.contract import ModuleSpec
from platforms.db import get_session
from platforms.gateway.app import create_app
from platforms.gateway.loader import ModuleLoadError, validate_spec


def test_platform_permissions_are_included_in_sync_list():
    synced = {permission.code for permission in registry.all_permissions()}
    assert {permission.code for permission in PLATFORM_PERMISSIONS} <= synced


def test_platform_menu_paths_match_declared_permissions():
    declared = {permission.code for permission in PLATFORM_PERMISSIONS}
    for menu in PLATFORM_MENUS:
        assert menu.permission in declared


def test_module_named_platform_is_rejected():
    spec = ModuleSpec(name="platform", title="冒充平台")
    with pytest.raises(ModuleLoadError, match="platform"):
        validate_spec(spec, "platform")


@pytest.fixture
async def client(session):
    app = create_app()

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _user(session, *, codes: tuple[str, ...] = ()) -> AppUser:
    user = AppUser(username=f"pp{id(session)}{len(codes)}", is_superuser=False, is_active=True)
    session.add(user)
    await session.flush()
    if codes:
        role = Role(code=f"r{user.id}", name="测试角色")
        session.add(role)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        for code in codes:
            permission = Permission(code=code, name=code, module=code.split(":", 1)[0])
            session.add(permission)
            await session.flush()
            session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await session.flush()
    return user


@pytest.mark.db
async def test_user_without_permission_sees_no_platform_menu(client, session):
    user = await _user(session)
    body = (await client.get("/api/modules", headers={"X-User-Id": str(user.id)})).json()
    assert body["platform_menus"] == []


@pytest.mark.db
async def test_user_with_permission_sees_platform_menu(client, session):
    user = await _user(session, codes=("platform:user:view",))
    body = (await client.get("/api/modules", headers={"X-User-Id": str(user.id)})).json()
    assert [menu["path"] for menu in body["platform_menus"]] == ["/platform/users"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_platform_permissions.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.auth.permissions'`

- [ ] **Step 3: 声明平台权限码与菜单**

创建 `server/platforms/auth/permissions.py`：

```python
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
```

- [ ] **Step 4: 并入权限同步列表**

把 `server/platforms/registry.py` 的 `all_permissions` 改成：

```python
def all_permissions() -> tuple[PermissionDef, ...]:
    """平台权限码也要进来，否则 sync_permissions 会把它们当成废弃权限删掉。"""
    from platforms.auth.permissions import PLATFORM_PERMISSIONS

    return PLATFORM_PERMISSIONS + tuple(
        permission for spec in _specs for permission in spec.permissions
    )
```

- [ ] **Step 5: 返回平台菜单**

在 `server/platforms/gateway/api.py` 的 `list_modules` 里，`return` 之前插入：

```python
    platform_menus = [
        {
            "title": menu.title,
            "path": menu.path,
            "icon": menu.icon,
            "order": menu.order,
            "parent": menu.parent,
            "permission": menu.permission,
        }
        for menu in sorted(PLATFORM_MENUS, key=lambda m: (m.order, m.path))
        if visible(menu.permission)
    ]
```

并把返回体改成：

```python
    return {
        "modules": modules,
        "platform_menus": platform_menus,
        "permissions": sorted({p.code for p in registry.all_permissions()} if superuser else codes),
        "superuser": superuser,
    }
```

顶部补 import：

```python
from platforms.auth.permissions import PLATFORM_MENUS
```

- [ ] **Step 6: 保留 platform 这个模块名**

在 `server/platforms/gateway/loader.py` 的 `validate_spec` 开头，`if spec.name != directory` 之前插入：

```python
    if spec.name == PLATFORM_MODULE_NAME:
        raise ModuleLoadError(f"模块名 {PLATFORM_MODULE_NAME!r} 为平台保留，会与平台权限码撞进同一命名空间")
```

顶部补 import：

```python
from platforms.auth.permissions import PLATFORM_MODULE_NAME
```

- [ ] **Step 7: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/ -v`
Expected: 全部 passed

- [ ] **Step 8: 同步权限点到库**

Run: `cd server && python scripts/sync_permissions.py`
Expected: 输出含「新增 4」（首次执行时）

- [ ] **Step 9: 提交**

```bash
git add server/platforms/auth/permissions.py server/platforms/registry.py server/platforms/gateway/api.py server/platforms/gateway/loader.py server/tests/platforms/test_platform_permissions.py
git commit -m "feat: 平台自身的权限码与系统管理菜单"
```

---

### Task 9: 用户与角色管理接口

**Files:**
- Create: `server/platforms/auth/admin_api.py`
- Modify: `server/platforms/gateway/app.py`
- Test: `server/tests/platforms/test_admin_api.py`

**Interfaces:**
- Consumes: Task 8 的权限码；现有 `require()`
- Produces: `platforms.auth.admin_api.router`，挂在 `/api/admin`，含
  `GET /users`、`PATCH /users/{user_id}/roles`、`PATCH /users/{user_id}/active`、
  `GET /roles`、`POST /roles`、`PATCH /roles/{role_id}`、`DELETE /roles/{role_id}`、`GET /permissions`

- [ ] **Step 1: 写失败的测试**

创建 `server/tests/platforms/test_admin_api.py`：

```python
"""用户与角色管理：权限闸门、角色分配生效、以及不许把自己锁在门外。"""

import pytest
from httpx import ASGITransport, AsyncClient

from platforms.auth.models import AppUser, Permission, Role, RolePermission, UserRole
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db


@pytest.fixture
async def client(session):
    app = create_app()

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _user(session, username: str, *, superuser: bool = False) -> AppUser:
    user = AppUser(username=username, display_name=username, is_superuser=superuser, is_active=True)
    session.add(user)
    await session.flush()
    return user


async def _role(session, code: str) -> Role:
    role = Role(code=code, name=code, description="")
    session.add(role)
    await session.flush()
    return role


def _as(user: AppUser) -> dict:
    return {"X-User-Id": str(user.id)}


async def test_user_list_requires_permission(client, session):
    plain = await _user(session, "plain")
    assert (await client.get("/api/admin/users", headers=_as(plain))).status_code == 403


async def test_superuser_can_list_users(client, session):
    admin = await _user(session, "admin", superuser=True)
    body = (await client.get("/api/admin/users", headers=_as(admin))).json()
    assert any(item["username"] == "admin" for item in body)


async def test_assigning_role_grants_permission_codes(client, session):
    admin = await _user(session, "admin2", superuser=True)
    target = await _user(session, "target")
    role = await _role(session, "ops")
    permission = Permission(code="example:item:view", name="查看条目", module="example")
    session.add(permission)
    await session.flush()
    session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await session.flush()

    response = await client.patch(
        f"/api/admin/users/{target.id}/roles", json={"role_ids": [role.id]}, headers=_as(admin)
    )

    assert response.status_code == 200
    modules = (await client.get("/api/modules", headers=_as(target))).json()
    assert "example:item:view" in modules["permissions"]


async def test_cannot_deactivate_self(client, session):
    admin = await _user(session, "admin3", superuser=True)
    response = await client.patch(
        f"/api/admin/users/{admin.id}/active", json={"is_active": False}, headers=_as(admin)
    )
    assert response.status_code == 400


async def test_deactivated_user_loses_access(client, session):
    admin = await _user(session, "admin4", superuser=True)
    target = await _user(session, "target4")

    await client.patch(f"/api/admin/users/{target.id}/active", json={"is_active": False}, headers=_as(admin))

    assert (await client.get("/api/admin/users", headers=_as(target))).status_code == 403


async def test_role_crud_round_trip(client, session):
    admin = await _user(session, "admin5", superuser=True)
    permission = Permission(code="example:item:create", name="创建条目", module="example")
    session.add(permission)
    await session.flush()

    created = await client.post(
        "/api/admin/roles",
        json={"code": "editor", "name": "编辑", "description": "", "permission_ids": [permission.id]},
        headers=_as(admin),
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    listed = (await client.get("/api/admin/roles", headers=_as(admin))).json()
    assert [role for role in listed if role["id"] == role_id][0]["permission_ids"] == [permission.id]

    updated = await client.patch(
        f"/api/admin/roles/{role_id}",
        json={"name": "编辑（改名）", "description": "", "permission_ids": []},
        headers=_as(admin),
    )
    assert updated.json()["name"] == "编辑（改名）"
    assert updated.json()["permission_ids"] == []

    assert (await client.delete(f"/api/admin/roles/{role_id}", headers=_as(admin))).status_code == 204
    assert all(role["id"] != role_id for role in (await client.get("/api/admin/roles", headers=_as(admin))).json())


async def test_duplicate_role_code_is_rejected(client, session):
    admin = await _user(session, "admin6", superuser=True)
    await _role(session, "dup")

    response = await client.post(
        "/api/admin/roles",
        json={"code": "dup", "name": "重复", "description": "", "permission_ids": []},
        headers=_as(admin),
    )
    assert response.status_code == 409


async def test_permission_list_is_grouped_by_module(client, session):
    admin = await _user(session, "admin7", superuser=True)
    session.add(Permission(code="example:item:view", name="查看条目", module="example"))
    await session.flush()

    body = (await client.get("/api/admin/permissions", headers=_as(admin))).json()

    assert any(group["module"] == "example" for group in body)


async def test_deleting_role_removes_user_binding(client, session):
    admin = await _user(session, "admin8", superuser=True)
    target = await _user(session, "target8")
    role = await _role(session, "temp")
    session.add(UserRole(user_id=target.id, role_id=role.id))
    await session.flush()

    await client.delete(f"/api/admin/roles/{role.id}", headers=_as(admin))

    users = (await client.get("/api/admin/users", headers=_as(admin))).json()
    assert [u for u in users if u["id"] == target.id][0]["role_ids"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && pytest tests/platforms/test_admin_api.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'platforms.auth.admin_api'`

- [ ] **Step 3: 实现管理接口**

创建 `server/platforms/auth/admin_api.py`：

```python
"""用户与角色管理，挂在 /api/admin 下。

资料字段来自飞书，这里只管「能不能进」和「能看见什么」，不提供编辑姓名头像的入口——
本地改了下次登录就被覆盖，留着只会让人困惑。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth.dependencies import require
from platforms.auth.models import AppUser, Permission, Role, RolePermission, UserIdentity, UserRole, UserSession
from platforms.auth.principal import Principal
from platforms.db import get_session

router = APIRouter()


class RoleIdsPayload(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class ActivePayload(BaseModel):
    is_active: bool


class RoleCreatePayload(BaseModel):
    code: str
    name: str
    description: str = ""
    permission_ids: list[int] = Field(default_factory=list)


class RoleUpdatePayload(BaseModel):
    name: str
    description: str = ""
    permission_ids: list[int] = Field(default_factory=list)


async def _role_ids_by_user(session: AsyncSession) -> dict[int, list[int]]:
    rows = (await session.execute(select(UserRole.user_id, UserRole.role_id))).all()
    grouped: dict[int, list[int]] = {}
    for user_id, role_id in rows:
        grouped.setdefault(user_id, []).append(role_id)
    return grouped


@router.get("/users", dependencies=[Depends(require("platform:user:view"))])
async def list_users(session: AsyncSession = Depends(get_session)):
    """一次返回全部用户。公司内部系统量级有限，真的慢了再加分页。"""
    stmt = (
        select(
            AppUser.id,
            AppUser.username,
            AppUser.display_name,
            AppUser.is_superuser,
            AppUser.is_active,
            UserIdentity.avatar_url,
            UserIdentity.email,
            UserIdentity.last_login_at,
        )
        .outerjoin(UserIdentity, UserIdentity.user_id == AppUser.id)
        .order_by(AppUser.id)
    )
    grouped = await _role_ids_by_user(session)
    return [
        {
            "id": row.id,
            "username": row.username,
            "display_name": row.display_name,
            "avatar_url": row.avatar_url or "",
            "email": row.email or "",
            "superuser": row.is_superuser,
            "is_active": row.is_active,
            "last_login_at": row.last_login_at,
            "role_ids": grouped.get(row.id, []),
        }
        for row in (await session.execute(stmt)).all()
    ]


@router.patch("/users/{user_id}/roles")
async def set_user_roles(
    user_id: int,
    payload: RoleIdsPayload,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require("platform:user:manage")),
):
    user = await session.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在。")

    known = set((await session.execute(select(Role.id).where(Role.id.in_(payload.role_ids)))).scalars())
    unknown = set(payload.role_ids) - known
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"角色不存在：{sorted(unknown)}")

    await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
    for role_id in sorted(known):
        session.add(UserRole(user_id=user_id, role_id=role_id))
    await session.flush()
    return {"id": user_id, "role_ids": sorted(known)}


@router.patch("/users/{user_id}/active")
async def set_user_active(
    user_id: int,
    payload: ActivePayload,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require("platform:user:manage")),
):
    if user_id == principal.user_id and not payload.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能停用自己的账号。")
    user = await session.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在。")

    user.is_active = payload.is_active
    if not payload.is_active:
        # 停用必须立刻生效，否则对方手里的会话还能继续用到过期为止。
        await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
    await session.flush()
    return {"id": user_id, "is_active": user.is_active}


async def _permission_ids_by_role(session: AsyncSession) -> dict[int, list[int]]:
    rows = (await session.execute(select(RolePermission.role_id, RolePermission.permission_id))).all()
    grouped: dict[int, list[int]] = {}
    for role_id, permission_id in rows:
        grouped.setdefault(role_id, []).append(permission_id)
    return grouped


def _role_body(role: Role, permission_ids: list[int], user_count: int) -> dict:
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "permission_ids": sorted(permission_ids),
        "user_count": user_count,
    }


@router.get("/roles", dependencies=[Depends(require("platform:role:view"))])
async def list_roles(session: AsyncSession = Depends(get_session)):
    roles = (await session.execute(select(Role).order_by(Role.id))).scalars().all()
    permissions = await _permission_ids_by_role(session)
    counts: dict[int, int] = {}
    for (role_id,) in (await session.execute(select(UserRole.role_id))).all():
        counts[role_id] = counts.get(role_id, 0) + 1
    return [_role_body(role, permissions.get(role.id, []), counts.get(role.id, 0)) for role in roles]


@router.post("/roles", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require("platform:role:manage"))])
async def create_role(payload: RoleCreatePayload, session: AsyncSession = Depends(get_session)):
    exists = (await session.execute(select(Role.id).where(Role.code == payload.code))).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"角色标识 {payload.code} 已存在。")

    role = Role(code=payload.code, name=payload.name, description=payload.description)
    session.add(role)
    await session.flush()
    await _replace_role_permissions(session, role.id, payload.permission_ids)
    return _role_body(role, payload.permission_ids, 0)


@router.patch("/roles/{role_id}", dependencies=[Depends(require("platform:role:manage"))])
async def update_role(role_id: int, payload: RoleUpdatePayload, session: AsyncSession = Depends(get_session)):
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")

    role.name = payload.name
    role.description = payload.description
    await _replace_role_permissions(session, role_id, payload.permission_ids)
    return _role_body(role, payload.permission_ids, 0)


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require("platform:role:manage"))],
)
async def delete_role(role_id: int, session: AsyncSession = Depends(get_session)):
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")
    # role_permission 与 user_role 的外键是 ON DELETE CASCADE，绑定关系会一并清掉。
    await session.delete(role)
    await session.flush()


async def _replace_role_permissions(session: AsyncSession, role_id: int, permission_ids: list[int]) -> None:
    known = set(
        (await session.execute(select(Permission.id).where(Permission.id.in_(permission_ids)))).scalars()
    )
    unknown = set(permission_ids) - known
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"权限点不存在：{sorted(unknown)}")
    await session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    for permission_id in sorted(known):
        session.add(RolePermission(role_id=role_id, permission_id=permission_id))
    await session.flush()


@router.get("/permissions", dependencies=[Depends(require("platform:role:view"))])
async def list_permissions(session: AsyncSession = Depends(get_session)):
    """按 module 分组返回，前端的勾选框直接照这个结构渲染。"""
    rows = (await session.execute(select(Permission).order_by(Permission.module, Permission.code))).scalars().all()
    grouped: dict[str, list[dict]] = {}
    for permission in rows:
        grouped.setdefault(permission.module, []).append(
            {"id": permission.id, "code": permission.code, "name": permission.name}
        )
    return [{"module": module, "permissions": items} for module, items in grouped.items()]
```

- [ ] **Step 4: 挂载路由**

在 `server/platforms/gateway/app.py` 中 `auth_router` 那行之后插入：

```python
    app.include_router(admin_router, prefix="/api/admin", tags=["platform"])
```

顶部补 import：

```python
from platforms.auth.admin_api import router as admin_router
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd server && pytest tests/platforms/test_admin_api.py -v`
Expected: 9 passed

- [ ] **Step 6: 全量回归**

Run: `cd server && pytest -q && ruff check . && alembic -n platform check`
Expected: 全部 passed，ruff 无告警，alembic 无 diff

- [ ] **Step 7: 提交**

```bash
git add server/platforms/auth/admin_api.py server/platforms/gateway/app.py server/tests/platforms/test_admin_api.py
git commit -m "feat: 用户与角色管理接口"
```

---

### Task 10: 前端会话状态

本任务只动 `shared/core` 的数据层，不碰路由——路由一旦引用尚未创建的视图文件，`typecheck` 就过不去，
中间状态不可验证。路由改造放在 Task 11、12，届时视图文件已经存在。

**Files:**
- Modify: `web/src/shared/core/request.ts`
- Create: `web/src/shared/core/session.ts`
- Modify: `web/src/shared/core/types.ts`
- Modify: `web/src/shared/core/index.ts`
- Modify: `web/src/shared/core/platform.ts`

**Interfaces:**
- Consumes: Task 7 的 `/api/auth/me`、`/logout`、`/feishu/login-url`、`/config`
- Produces:
  - `SessionUser`：`{ id: number; username: string; display_name: string; avatar_url: string; superuser: boolean }`
  - `useSessionStore()`：`user` / `loaded` / `load()` / `logout()` / `startFeishuLogin()`
  - `PlatformProfile` 新增 `platform_menus: MenuInfo[]`
  - `usePlatformStore().platformMenus`

- [ ] **Step 1: 请求携带 cookie**

把 `web/src/shared/core/request.ts` 的 `buildHeaders` 与 `request` 改成：

```ts
function buildHeaders(init?: RequestInit): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string>) ?? {}),
  }
  // 后端 AUTH_MODE=dev_header 时用它模拟身份；接飞书登录后应在 .env.local 里删掉这一项
  const devUserId = import.meta.env.VITE_DEV_USER_ID
  if (devUserId) {
    headers['X-User-Id'] = devUserId
  }
  return headers
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: 'include',
    headers: buildHeaders(init),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const error = new Error(body.message ?? response.statusText) as ApiError
    error.status = response.status
    error.requestId = body.request_id
    throw error
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}
```

- [ ] **Step 2: 加会话 store**

创建 `web/src/shared/core/session.ts`：

```ts
/** 当前登录用户。未登录时后端返回 401，store 保持 user=null，由路由守卫跳登录页。 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

import { request } from './request'
import type { ApiError, SessionUser } from './types'

export const useSessionStore = defineStore('session', () => {
  const user = ref<SessionUser | null>(null)
  const loaded = ref(false)

  async function load(): Promise<void> {
    try {
      user.value = await request<SessionUser>('/auth/me')
    } catch (e) {
      if ((e as ApiError).status !== 401) throw e
      user.value = null
    } finally {
      loaded.value = true
    }
  }

  async function startFeishuLogin(): Promise<void> {
    const { authorize_url } = await request<{ authorize_url: string }>('/auth/feishu/login-url', {
      method: 'POST',
    })
    window.location.href = authorize_url
  }

  async function logout(): Promise<void> {
    await request<void>('/auth/logout', { method: 'POST' })
    user.value = null
    loaded.value = false
    window.location.href = '/login'
  }

  return { user, loaded, load, logout, startFeishuLogin }
})
```

- [ ] **Step 3: 补类型**

在 `web/src/shared/core/types.ts` 末尾追加，并给 `PlatformProfile` 加字段：

```ts
export interface SessionUser {
  id: number
  username: string
  display_name: string
  avatar_url: string
  superuser: boolean
}
```

`PlatformProfile` 改为：

```ts
export interface PlatformProfile {
  modules: ModuleInfo[]
  platform_menus: MenuInfo[]
  permissions: string[]
  superuser: boolean
}
```

`web/src/shared/core/index.ts` 追加导出：

```ts
export { useSessionStore } from './session'
export type { SessionUser } from './types'
```

- [ ] **Step 4: platform store 暴露平台菜单**

在 `web/src/shared/core/platform.ts` 中，`const loaded = ref(false)` 之后加：

```ts
  const platformMenus = ref<MenuInfo[]>([])
```

`load()` 里 `modules.value = profile.modules` 之后加：

```ts
    platformMenus.value = profile.platform_menus
```

返回值里加上 `platformMenus`。

- [ ] **Step 5: 校验**

Run: `cd web && npm run lint && npm run typecheck`
Expected: 均通过（本任务没有引用任何尚不存在的文件）

- [ ] **Step 6: 提交**

```bash
git add web/src/shared/core/
git commit -m "feat: 前端会话状态与请求携带 cookie"
```

---

### Task 11: 登录页、粒子动画与登录守卫

**Files:**
- Create: `web/src/shell/components/ParticleField.vue`
- Create: `web/src/shell/views/LoginView.vue`
- Modify: `web/src/shell/router.ts`

**Interfaces:**
- Consumes: Task 10 的 `useSessionStore()`
- Produces: `/login` 路由与「未登录跳登录页」的守卫；登录页读取 `?error=` 展示回调失败原因

登录页用 `<style scoped>` 自带深色样式，不需要往 `shared/ui/styles.css` 加全局 token——
那份文件是给浅色工作区用的，掺进登录页专用的深色变量只会让主题变量失去意义。

- [ ] **Step 1: 粒子动画组件**

创建 `web/src/shell/components/ParticleField.vue`。逻辑移植自 `advertising-center` 的 `LoginParticleField`，只把 React 的 `useEffect` 换成 Vue 生命周期：

```vue
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canvasRef = ref<HTMLCanvasElement | null>(null)
let frame = 0
let cleanup: (() => void) | null = null

onMounted(() => {
  const canvas = canvasRef.value
  const context = canvas?.getContext('2d')
  if (!canvas || !context) return

  const pointer = { x: -9999, y: -9999, active: false }
  const particles: Array<{ x: number; y: number; vx: number; vy: number; size: number; tone: number; hover: number }> = []
  const palette = ['#2f7fff', '#19c7b7', '#80b4ff']
  let width = 0
  let height = 0

  function resize(): void {
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    width = canvas!.clientWidth
    height = canvas!.clientHeight
    canvas!.width = Math.round(width * ratio)
    canvas!.height = Math.round(height * ratio)
    context!.setTransform(ratio, 0, 0, ratio, 0, 0)
    particles.length = 0
    const count = Math.min(170, Math.max(90, Math.round((width * height) / 10500)))
    for (let index = 0; index < count; index += 1) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.42,
        vy: (Math.random() - 0.5) * 0.42,
        size: 1.5 + Math.random() * 2.1,
        tone: index % palette.length,
        hover: 0,
      })
    }
  }

  function onPointerMove(event: PointerEvent): void {
    const bounds = canvas!.getBoundingClientRect()
    pointer.x = event.clientX - bounds.left
    pointer.y = event.clientY - bounds.top
    pointer.active = pointer.x >= 0 && pointer.x <= width && pointer.y >= 0 && pointer.y <= height
  }

  function onPointerLeave(): void {
    pointer.active = false
  }

  function draw(): void {
    context!.clearRect(0, 0, width, height)

    for (const particle of particles) {
      const dx = particle.x - pointer.x
      const dy = particle.y - pointer.y
      const distance = Math.hypot(dx, dy) || 1
      const influence = pointer.active ? Math.max(0, 1 - distance / 230) : 0
      if (influence > 0) {
        particle.vx += (dx / distance) * influence * 0.18
        particle.vy += (dy / distance) * influence * 0.18
      }
      particle.hover += (influence - particle.hover) * 0.16
      particle.vx *= 0.992
      particle.vy *= 0.992
      particle.x += particle.vx
      particle.y += particle.vy
      if (particle.x < -12) particle.x = width + 12
      if (particle.x > width + 12) particle.x = -12
      if (particle.y < -12) particle.y = height + 12
      if (particle.y > height + 12) particle.y = -12
    }

    for (let first = 0; first < particles.length; first += 1) {
      for (let second = first + 1; second < particles.length; second += 1) {
        const a = particles[first]
        const b = particles[second]
        const distance = Math.hypot(a.x - b.x, a.y - b.y)
        if (distance > 146) continue
        const alpha = (1 - distance / 146) * (0.2 + Math.max(a.hover, b.hover) * 0.42)
        context!.beginPath()
        context!.moveTo(a.x, a.y)
        context!.lineTo(b.x, b.y)
        context!.strokeStyle = `rgba(72, 142, 255, ${alpha})`
        context!.lineWidth = 0.9 + Math.max(a.hover, b.hover) * 0.6
        context!.stroke()
      }
    }

    for (const particle of particles) {
      context!.beginPath()
      context!.arc(particle.x, particle.y, particle.size + particle.hover * 2.7, 0, Math.PI * 2)
      context!.fillStyle = particle.hover > 0.32 ? '#d6e6ff' : palette[particle.tone]
      context!.globalAlpha = 0.54 + particle.hover * 0.46
      context!.fill()
    }
    context!.globalAlpha = 1
    frame = window.requestAnimationFrame(draw)
  }

  resize()
  draw()
  window.addEventListener('resize', resize)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('pointerleave', onPointerLeave)
  cleanup = () => {
    window.cancelAnimationFrame(frame)
    window.removeEventListener('resize', resize)
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerleave', onPointerLeave)
  }
})

onBeforeUnmount(() => cleanup?.())
</script>

<template>
  <canvas ref="canvasRef" class="particle-field" aria-hidden="true" />
</template>

<style scoped>
.particle-field {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
</style>
```

- [ ] **Step 2: 登录页**

创建 `web/src/shell/views/LoginView.vue`：

```vue
<script setup lang="ts">
import { useSessionStore } from '@shared/core'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import ParticleField from '../components/ParticleField.vue'

const session = useSessionStore()
const route = useRoute()
const error = ref((route.query.error as string) ?? '')
const feishuConfigured = ref(true)
const starting = ref(false)

onMounted(async () => {
  try {
    const config = await fetch('/api/auth/config').then((r) => r.json())
    feishuConfigured.value = config.feishu_configured
  } catch {
    feishuConfigured.value = false
  }
})

async function login(): Promise<void> {
  starting.value = true
  error.value = ''
  try {
    await session.startFeishuLogin()
  } catch (e) {
    error.value = (e as Error).message
    starting.value = false
  }
}
</script>

<template>
  <main class="login">
    <ParticleField />
    <header class="topbar">
      <span class="mark">L</span>
      <strong>lancha-ai-studio</strong>
    </header>
    <section class="copy">
      <h1>AI 内容<br />生产与运营平台</h1>
    </section>
    <section class="panel">
      <div class="panel-mark" aria-hidden="true"><span>飞</span></div>
      <h2>飞书登录</h2>
      <button type="button" :disabled="starting || !feishuConfigured" @click="login">
        {{ starting ? '正在打开飞书…' : '飞书登录' }}
      </button>
      <p v-if="!feishuConfigured" class="notice">后端尚未配置飞书应用，请联系管理员。</p>
      <p v-if="error" class="notice">{{ error }}</p>
    </section>
  </main>
</template>

<style scoped>
.login {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 420px);
  align-items: center;
  min-height: 100vh;
  gap: clamp(32px, 6vw, 112px);
  padding: 108px clamp(32px, 8vw, 152px) 64px;
  background: #161d28;
}

.topbar {
  position: absolute;
  top: 28px;
  left: clamp(32px, 8vw, 152px);
  display: inline-flex;
  align-items: center;
  gap: 11px;
  color: rgba(255, 255, 255, 0.92);
  font-size: 15px;
}

.mark {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 7px;
  background: #255fd0;
  color: #fff;
  font-weight: 900;
}

.copy,
.panel {
  position: relative;
}

.copy h1 {
  max-width: 700px;
  color: #fff;
  font-size: 46px;
  line-height: 1.18;
}

.panel {
  justify-self: end;
  width: 100%;
  padding: 34px;
  border: 1px solid rgba(184, 203, 237, 0.2);
  border-radius: 10px;
  background: #242b35;
  box-shadow: 0 22px 54px rgba(0, 0, 0, 0.24);
}

.panel-mark span {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 9px;
  background: #255fd0;
  color: #fff;
  font-weight: 900;
}

.panel h2 {
  margin: 18px 0 22px;
  color: #fff;
  font-size: 22px;
}

.panel button {
  width: 100%;
  height: 42px;
  border: 0;
  border-radius: 7px;
  background: #255fd0;
  color: #fff;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
}

.panel button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.notice {
  margin: 14px 0 0;
  color: #ff9c9c;
  font-size: 13px;
  line-height: 1.7;
}

@media (max-width: 960px) {
  .login {
    grid-template-columns: 1fr;
    padding: 100px 28px 42px;
  }

  .panel {
    justify-self: stretch;
  }

  .copy h1 {
    font-size: 34px;
  }
}
</style>
```

- [ ] **Step 3: 接入路由与登录守卫**

把 `web/src/shell/router.ts` 的 `createAppRouter` 改成：

```ts
export function createAppRouter(modules: AppModule[]) {
  const children: RouteRecordRaw[] = [
    { path: '', name: 'home', component: () => import('./views/HomeView.vue') },
    ...modules.flatMap(prefixRoutes),
  ]

  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/login', name: 'login', component: () => import('./views/LoginView.vue') },
      { path: '/', component: AppLayout, children },
      { path: '/403', name: 'forbidden', component: () => import('./views/ForbiddenView.vue') },
      { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue') },
    ],
  })

  router.beforeEach(async (to) => {
    const session = useSessionStore()
    if (!session.loaded) {
      // 后端没起时不阻塞登录页，其余页面按未登录处理
      await session.load().catch(() => undefined)
    }
    if (to.name === 'login') {
      return session.user ? { path: '/' } : true
    }
    if (!session.user) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    const store = usePlatformStore()
    if (!store.loaded) {
      await store.load().catch(() => undefined)
    }
    const code = to.meta.permission as string | undefined
    return code && !store.has(code) ? { name: 'forbidden' } : true
  })

  return router
}
```

顶部 import 改为：

```ts
import { usePlatformStore, useSessionStore } from '@shared/core'
```

- [ ] **Step 4: 校验**

Run: `cd web && npm run lint && npm run typecheck`
Expected: 均通过

- [ ] **Step 5: 跑通真实登录**

后端设 `AUTH_MODE=feishu` 并填齐飞书配置，前端 `npm run dev`，访问 `http://localhost:5173/`。
Expected: 自动跳到 `/login`，看到深色页面、粒子随鼠标聚拢、右侧登录卡片；点「飞书登录」扫码后回到首页，
再访问 `/login` 会被守卫弹回首页。

- [ ] **Step 6: 提交**

```bash
git add web/src/shell/components/ParticleField.vue web/src/shell/views/LoginView.vue web/src/shell/router.ts
git commit -m "feat: 飞书登录页、粒子背景与登录守卫"
```

---

### Task 12: 用户区、用户管理页与角色管理页

**Files:**
- Create: `web/src/shell/api/platform.ts`
- Create: `web/src/shell/views/UsersView.vue`
- Create: `web/src/shell/views/RolesView.vue`
- Modify: `web/src/shell/layout/AppLayout.vue`
- Modify: `web/src/shell/router.ts`

**Interfaces:**
- Consumes: Task 9 的八个管理接口；Task 10 的 `useSessionStore` / `usePlatformStore().platformMenus`
- Produces: `/platform/users` 与 `/platform/roles` 两个页面

页面里的权限控制一律用 `:disabled="!platform.has('...')"`，不用 `v-permission`。
`v-permission` 的实现是把元素从 DOM 移除，放在 `v-for` 渲染出的行内会破坏列表结构；
禁用态也比「按钮凭空消失」更容易让人理解自己为什么不能操作。

- [ ] **Step 1: API 封装**

创建 `web/src/shell/api/platform.ts`：

```ts
/** 平台管理接口。shell 自己的能力，不属于任何业务模块。 */

import { request } from '@shared/core'

export interface ManagedUser {
  id: number
  username: string
  display_name: string
  avatar_url: string
  email: string
  superuser: boolean
  is_active: boolean
  last_login_at: string | null
  role_ids: number[]
}

export interface ManagedRole {
  id: number
  code: string
  name: string
  description: string
  permission_ids: number[]
  user_count: number
}

export interface PermissionGroup {
  module: string
  permissions: Array<{ id: number; code: string; name: string }>
}

export const listUsers = () => request<ManagedUser[]>('/admin/users')

export const setUserRoles = (id: number, roleIds: number[]) =>
  request<void>(`/admin/users/${id}/roles`, { method: 'PATCH', body: JSON.stringify({ role_ids: roleIds }) })

export const setUserActive = (id: number, isActive: boolean) =>
  request<void>(`/admin/users/${id}/active`, { method: 'PATCH', body: JSON.stringify({ is_active: isActive }) })

export const listRoles = () => request<ManagedRole[]>('/admin/roles')

export const createRole = (payload: Omit<ManagedRole, 'id' | 'user_count'>) =>
  request<ManagedRole>('/admin/roles', { method: 'POST', body: JSON.stringify(payload) })

export const updateRole = (id: number, payload: Omit<ManagedRole, 'id' | 'code' | 'user_count'>) =>
  request<ManagedRole>(`/admin/roles/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteRole = (id: number) => request<void>(`/admin/roles/${id}`, { method: 'DELETE' })

export const listPermissions = () => request<PermissionGroup[]>('/admin/permissions')
```

- [ ] **Step 2: 用户管理页**

创建 `web/src/shell/views/UsersView.vue`：

```vue
<script setup lang="ts">
import { usePlatformStore } from '@shared/core'
import { computed, onMounted, ref } from 'vue'

import { listRoles, listUsers, setUserActive, setUserRoles, type ManagedRole, type ManagedUser } from '../api/platform'

const platform = usePlatformStore()
const canManage = computed(() => platform.has('platform:user:manage'))
const users = ref<ManagedUser[]>([])
const roles = ref<ManagedRole[]>([])
const error = ref('')

async function refresh(): Promise<void> {
  try {
    ;[users.value, roles.value] = await Promise.all([listUsers(), listRoles()])
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function toggleRole(user: ManagedUser, roleId: number): Promise<void> {
  const next = user.role_ids.includes(roleId)
    ? user.role_ids.filter((id) => id !== roleId)
    : [...user.role_ids, roleId]
  try {
    await setUserRoles(user.id, next)
    user.role_ids = next
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function toggleActive(user: ManagedUser): Promise<void> {
  try {
    await setUserActive(user.id, !user.is_active)
    user.is_active = !user.is_active
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <section>
    <h1>用户管理</h1>
    <p v-if="error" class="error">{{ error }}</p>
    <table>
      <thead>
        <tr>
          <th>用户</th>
          <th>邮箱</th>
          <th>角色</th>
          <th>状态</th>
          <th>最后登录</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in users" :key="user.id">
          <td class="who">
            <img v-if="user.avatar_url" :src="user.avatar_url" alt="" />
            <span>{{ user.display_name || user.username }}</span>
            <em v-if="user.superuser">超级管理员</em>
          </td>
          <td>{{ user.email }}</td>
          <td class="roles">
            <label v-for="role in roles" :key="role.id">
              <input
                type="checkbox"
                :checked="user.role_ids.includes(role.id)"
                :disabled="!canManage"
                @change="toggleRole(user, role.id)"
              />
              {{ role.name }}
            </label>
            <span v-if="roles.length === 0" class="muted">先在角色管理里创建角色</span>
          </td>
          <td>
            <button type="button" :disabled="!canManage" @click="toggleActive(user)">
              {{ user.is_active ? '停用' : '启用' }}
            </button>
            <span v-if="!user.is_active" class="muted">已停用</span>
          </td>
          <td class="muted">{{ user.last_login_at ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
table {
  width: 100%;
  margin-top: var(--space-md);
  border-collapse: collapse;
  background: var(--color-surface);
}

th,
td {
  padding: 10px var(--space-sm);
  border-bottom: 1px solid var(--color-border);
  font-size: 14px;
  text-align: left;
}

th {
  color: var(--color-text-weak);
  font-size: 12px;
  font-weight: 500;
}

.who {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.who img {
  width: 28px;
  height: 28px;
  border-radius: 50%;
}

.who em {
  padding: 1px 6px;
  border-radius: var(--radius);
  background: var(--color-bg);
  color: var(--color-primary);
  font-size: 11px;
  font-style: normal;
}

.roles {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.roles label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.muted {
  color: var(--color-text-weak);
  font-size: 12px;
}

.error {
  color: #d03050;
}
</style>
```

- [ ] **Step 3: 角色管理页**

创建 `web/src/shell/views/RolesView.vue`：

```vue
<script setup lang="ts">
import { usePlatformStore } from '@shared/core'
import { computed, onMounted, ref } from 'vue'

import {
  createRole,
  deleteRole,
  listPermissions,
  listRoles,
  updateRole,
  type ManagedRole,
  type PermissionGroup,
} from '../api/platform'

const platform = usePlatformStore()
const canManage = computed(() => platform.has('platform:role:manage'))
const roles = ref<ManagedRole[]>([])
const groups = ref<PermissionGroup[]>([])
const editing = ref<ManagedRole | null>(null)
const draft = ref({ code: '', name: '', description: '', permission_ids: [] as number[] })
const error = ref('')

async function refresh(): Promise<void> {
  try {
    ;[roles.value, groups.value] = await Promise.all([listRoles(), listPermissions()])
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

function startCreate(): void {
  editing.value = null
  draft.value = { code: '', name: '', description: '', permission_ids: [] }
}

function startEdit(role: ManagedRole): void {
  editing.value = role
  draft.value = {
    code: role.code,
    name: role.name,
    description: role.description,
    permission_ids: [...role.permission_ids],
  }
}

function togglePermission(id: number): void {
  const current = draft.value.permission_ids
  draft.value.permission_ids = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
}

async function submit(): Promise<void> {
  try {
    if (editing.value) {
      await updateRole(editing.value.id, {
        name: draft.value.name,
        description: draft.value.description,
        permission_ids: draft.value.permission_ids,
      })
    } else {
      await createRole(draft.value)
    }
    startCreate()
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function remove(role: ManagedRole): Promise<void> {
  try {
    await deleteRole(role.id)
    if (editing.value?.id === role.id) startCreate()
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <section>
    <h1>角色管理</h1>
    <p v-if="error" class="error">{{ error }}</p>

    <table>
      <thead>
        <tr>
          <th>角色</th>
          <th>标识</th>
          <th>权限数</th>
          <th>用户数</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="role in roles" :key="role.id">
          <td>{{ role.name }}</td>
          <td class="muted">{{ role.code }}</td>
          <td>{{ role.permission_ids.length }}</td>
          <td>{{ role.user_count }}</td>
          <td>
            <button type="button" :disabled="!canManage" @click="startEdit(role)">编辑</button>
            <button type="button" :disabled="!canManage" @click="remove(role)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <form v-if="canManage" @submit.prevent="submit">
      <h2>{{ editing ? `编辑角色：${editing.name}` : '新建角色' }}</h2>
      <div class="fields">
        <input v-model="draft.code" :disabled="!!editing" placeholder="标识，如 ops" required />
        <input v-model="draft.name" placeholder="名称，如 运营" required />
        <input v-model="draft.description" placeholder="说明（可选）" />
      </div>
      <div v-for="group in groups" :key="group.module" class="group">
        <h3>{{ group.module }}</h3>
        <label v-for="permission in group.permissions" :key="permission.id">
          <input
            type="checkbox"
            :checked="draft.permission_ids.includes(permission.id)"
            @change="togglePermission(permission.id)"
          />
          {{ permission.name }}<em>{{ permission.code }}</em>
        </label>
      </div>
      <div class="actions">
        <button type="submit">{{ editing ? '保存' : '创建' }}</button>
        <button v-if="editing" type="button" @click="startCreate()">取消</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
table {
  width: 100%;
  margin-top: var(--space-md);
  border-collapse: collapse;
  background: var(--color-surface);
}

th,
td {
  padding: 10px var(--space-sm);
  border-bottom: 1px solid var(--color-border);
  font-size: 14px;
  text-align: left;
}

th {
  color: var(--color-text-weak);
  font-size: 12px;
  font-weight: 500;
}

form {
  margin-top: var(--space-lg);
  padding: var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
}

h2 {
  margin: 0 0 var(--space-md);
  font-size: 15px;
}

.fields {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

input {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}

.group {
  margin-bottom: var(--space-md);
}

.group h3 {
  margin: 0 0 var(--space-sm);
  color: var(--color-text-weak);
  font-size: 12px;
  font-weight: 500;
}

.group label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-right: var(--space-md);
  font-size: 14px;
}

.group em {
  margin-left: 4px;
  color: var(--color-text-weak);
  font-size: 11px;
  font-style: normal;
}

.actions {
  display: flex;
  gap: var(--space-sm);
}

button {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  cursor: pointer;
}

.muted {
  color: var(--color-text-weak);
}

.error {
  color: #d03050;
}
</style>
```

- [ ] **Step 4: AppLayout 加用户区与平台菜单**

把 `web/src/shell/layout/AppLayout.vue` 的 `<script setup>` 与 `<template>` 改成：

```vue
<script setup lang="ts">
import { usePlatformStore, useSessionStore } from '@shared/core'

const platform = usePlatformStore()
const session = useSessionStore()
</script>

<template>
  <div class="layout">
    <aside class="sider">
      <div class="brand">lancha-ai-studio</div>
      <nav>
        <p v-if="platform.menuTree.length === 0 && platform.platformMenus.length === 0" class="empty">
          暂无可见菜单
        </p>
        <section v-for="group in platform.menuTree" :key="group.path" class="group">
          <h3>{{ group.title }}</h3>
          <RouterLink v-for="menu in group.children" :key="menu.path" :to="menu.path" class="item">
            {{ menu.title }}
          </RouterLink>
        </section>
        <section v-if="platform.platformMenus.length > 0" class="group">
          <h3>系统管理</h3>
          <RouterLink v-for="menu in platform.platformMenus" :key="menu.path" :to="menu.path" class="item">
            {{ menu.title }}
          </RouterLink>
        </section>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <span v-if="session.user" class="who">
          <img v-if="session.user.avatar_url" :src="session.user.avatar_url" alt="" />
          {{ session.user.display_name || session.user.username }}
        </span>
        <button type="button" @click="session.logout()">退出登录</button>
      </header>
      <main class="content">
        <RouterView />
      </main>
    </div>
  </div>
</template>
```

`<style scoped>` 保留原有内容，并追加：

```css
.main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-md);
  height: 52px;
  padding: 0 var(--space-lg);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
}

.who {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: 14px;
}

.who img {
  width: 26px;
  height: 26px;
  border-radius: 50%;
}

.topbar button {
  padding: 5px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  cursor: pointer;
}
```

`.content` 的规则保持原样，它现在是 `.main` 的子元素，`flex: 1` 继续生效。

- [ ] **Step 5: 挂上两条平台路由**

在 `web/src/shell/router.ts` 的 `children` 数组里，`home` 之后插入：

```ts
    {
      path: 'platform/users',
      name: 'platform/users',
      component: () => import('./views/UsersView.vue'),
      meta: { permission: 'platform:user:view' },
    },
    {
      path: 'platform/roles',
      name: 'platform/roles',
      component: () => import('./views/RolesView.vue'),
      meta: { permission: 'platform:role:view' },
    },
```

- [ ] **Step 6: 前端校验**

Run: `cd web && npm run lint && npm run typecheck`
Expected: 均通过

- [ ] **Step 7: 手工验证**

以超管身份登录，侧边栏出现「系统管理」分组。
Expected: 角色管理里能建角色并勾权限；用户管理里把角色分配给另一个用户后，对方刷新即可见对应菜单；
停用自己会收到「不能停用自己的账号。」

- [ ] **Step 8: 提交**

```bash
git add web/src/shell/
git commit -m "feat: 用户管理页、角色管理页与顶栏用户区"
```

---

### Task 13: 配置样例与文档更新

**Files:**
- Modify: `server/.env.example`
- Modify: `web/.env.example`
- Modify: `README.md`
- Modify: `docs/架构规范.md`

**Interfaces:**
- Consumes: 前面所有任务
- Produces: 可照着跑通的本地启动步骤

- [ ] **Step 1: 后端配置样例**

在 `server/.env.example` 的 `ENABLED_MODULES=` 之后插入：

```
# 认证方式：dev_header 用 X-User-Id 请求头（仅限本地开发），feishu 走飞书扫码登录
AUTH_MODE=dev_header

# 飞书应用凭证，AUTH_MODE=feishu 时必填
FEISHU_APP_ID=
FEISHU_APP_SECRET=
# 飞书会把浏览器直接重定向到这里，开发期必须填前端地址（经 Vite 代理转发），
# 填后端地址会让 cookie 落在后端域下，前端带不过去，表现为「回调成功但仍未登录」
FEISHU_REDIRECT_URI=http://localhost:5173/api/auth/feishu/callback
FEISHU_SCOPE=auth:user.id:read contact:user.employee:readonly

# 会话有效期；生产环境走 HTTPS 时把 COOKIE_SECURE 置为 true
SESSION_TTL_DAYS=7
COOKIE_SECURE=false
FRONTEND_BASE_URL=http://localhost:5173
```

- [ ] **Step 2: 前端配置样例**

把 `web/.env.example` 最后一段改成：

```
# 后端 AUTH_MODE=dev_header 时用这个用户 ID 调接口；切到飞书登录后请删掉这一行
VITE_DEV_USER_ID=1
```

- [ ] **Step 3: README 补飞书登录段落**

在 `README.md` 的「本框架不含认证」那段之后替换为：

```markdown
## 认证

默认 `AUTH_MODE=dev_header`，身份由 `X-User-Id` 请求头模拟，需要先建一个用户：

```sql
INSERT INTO platform."user" (id, username, display_name, is_superuser, is_active)
VALUES (1, 'admin', 'admin', true, true);
```

切换到飞书登录：在 `server/.env` 里设 `AUTH_MODE=feishu` 并填齐 `FEISHU_APP_ID` /
`FEISHU_APP_SECRET` / `FEISHU_REDIRECT_URI`，同时删掉 `web/.env.local` 的 `VITE_DEV_USER_ID`。
飞书开放平台的重定向 URL 要与 `FEISHU_REDIRECT_URI` 完全一致。

第一个超级管理员仍然手工指定——飞书扫码登录一次，再执行：

```sql
UPDATE platform."user" SET is_superuser = true WHERE username = '你的企业邮箱';
```

之后就能在「系统管理 → 角色管理」里建角色，在「用户管理」里把角色分配给其他人。
```

- [ ] **Step 4: 更新架构规范**

`docs/架构规范.md` 第 4 节首句改为：

```markdown
本框架做授权（RBAC）与认证（飞书扫码登录，可替换）。
```

同节第二条改为：

```markdown
- 当前请求属于谁，由 `platforms/auth/principal.py` 决定。`AUTH_MODE=dev_header` 时从 `X-User-Id` 请求头取，**仅供开发自测**；`AUTH_MODE=feishu` 时由 `create_app()` 装上基于会话 cookie 的实现。换成公司自有账号系统时只需替换 `platforms/auth/feishu/`，`session.py` 与 `identity.py` 不动。
```

第 9 节「当前刻意不做的事」删掉「认证与登录」，并在句尾补一句：

```markdown
认证已接入飞书扫码登录（见第 4 节），多 provider 注册表尚未抽象——等出现第二个真实实现时再提取。
```

- [ ] **Step 5: 端到端验收**

按设计文档的七条验收标准逐条走一遍：

```bash
cd server && alembic -n platform upgrade head && alembic -n platform check
cd server && python scripts/sync_permissions.py
cd server && pytest -q && ruff check .
cd web && npm run lint && npm run typecheck
```

然后 `AUTH_MODE=feishu` 启动前后端，真实扫码走通：未登录跳 `/login` → 扫码 → 进首页看到头像姓名 →
用超管建角色并分配 → 刷新后菜单出现 → 退出登录跳回 `/login`。

- [ ] **Step 6: 提交**

```bash
git add server/.env.example web/.env.example README.md docs/架构规范.md
git commit -m "docs: 飞书登录的配置说明与规范更新"
```
