"""RBAC 与会话表，全部建在 platform schema 下。

user 只存身份标识，不存任何凭证：第三方账号绑定在 user_identity，会话在 user_session，
两者都只认 user.id。换登录方式时只动这两张表的写入方，RBAC 部分不受影响。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from platforms.db import PLATFORM_SCHEMA, Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AppUser(TimestampMixin, Base):
    """
    平台内部账户主表。没有密码或外部 access token；所有授权和会话最终关联它的 ID。
    """
    __tablename__ = "user"
    __table_args__ = {"schema": PLATFORM_SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)   # 跳过所有权限校验
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Role(TimestampMixin, Base):
    """可分配给用户的一组授权集合。"""
    __tablename__ = "role"
    __table_args__ = {"schema": PLATFORM_SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255), default="")


class Permission(Base):
    """权限点由各模块 module.py 声明，用 scripts/sync_permissions.py 同步到这张表。"""

    __tablename__ = "permission"
    __table_args__ = {"schema": PLATFORM_SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    module: Mapped[str] = mapped_column(String(64), index=True)


class UserRole(Base):
    """用户与角色的多对多关联；删除用户或角色时关联级联清理。"""
    __tablename__ = "user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        {"schema": PLATFORM_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(f"{PLATFORM_SCHEMA}.user.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey(f"{PLATFORM_SCHEMA}.role.id", ondelete="CASCADE"))


class RolePermission(Base):
    __tablename__ = "role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        {"schema": PLATFORM_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey(f"{PLATFORM_SCHEMA}.role.id", ondelete="CASCADE"))
    permission_id: Mapped[int] = mapped_column(ForeignKey(f"{PLATFORM_SCHEMA}.permission.id", ondelete="CASCADE"))


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
    """OAuth 一次性 state，同样只存哈希，消费时用带有有效期的 DELETE RETURNING。

    nonce_hash 把 state 绑到发起登录的那个浏览器上：明文 nonce 只在发起方的 HttpOnly cookie 里，
    回调时两边不匹配就拒绝。没有它，任何人拿到的 state 在任何人的浏览器里都有效，
    攻击者就能把指向自己账号的回调地址诱导给受害者点开（login CSRF）。
    """

    __tablename__ = "oauth_state"
    __table_args__ = {"schema": PLATFORM_SCHEMA}

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
