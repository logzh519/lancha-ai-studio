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
