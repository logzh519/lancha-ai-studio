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
