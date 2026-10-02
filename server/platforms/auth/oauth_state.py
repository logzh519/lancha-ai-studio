"""OAuth 一次性 state。

消费用带有效期条件的 DELETE ... RETURNING，查和删在同一条语句里完成，
并发回调不会出现「两次都通过」的窗口。

state 之外还发一个 nonce：明文只写进发起方浏览器的 HttpOnly cookie，库里存哈希，
回调时必须两边对得上。单靠 state 挡不住 login CSRF——它对任何浏览器都有效。
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth.models import OAuthState
from platforms.auth.session import hash_token

# 与会话 cookie 分开：生命周期只有一次回调，且回调处理完无论成败都要删掉。
NONCE_COOKIE = "lancha_oauth_nonce"


async def create(session: AsyncSession, ttl: timedelta) -> tuple[str, str]:
    """新建一条 state，返回（原始 state, 原始 nonce），调用方负责把 nonce 写进 cookie。"""
    raw_state = secrets.token_urlsafe(24)
    raw_nonce = secrets.token_urlsafe(24)
    # 顺手清理过期行：这张表由匿名、无频率限制的 login-url 写入，没人清就只会一直涨。
    # 不做定时任务是因为仓库里没有调度器，而这里恰好是唯一的写入口——灌得越狠清得越勤。
    await session.execute(delete(OAuthState).where(OAuthState.expires_at <= datetime.now(timezone.utc)))
    session.add(
        OAuthState(
            state_hash=hash_token(raw_state),
            nonce_hash=hash_token(raw_nonce),
            expires_at=datetime.now(timezone.utc) + ttl,
        )
    )
    await session.flush()
    return raw_state, raw_nonce


async def consume(session: AsyncSession, raw_state: str) -> str | None:
    """消费 state，返回它绑定的 nonce_hash；state 无效或已过期返回 None。

    nonce 跟着同一条 DELETE RETURNING 一起带出来，不拆成「先查再删」——拆了就又有重放窗口。
    """
    if not raw_state:
        return None
    stmt = (
        delete(OAuthState)
        .where(
            OAuthState.state_hash == hash_token(raw_state),
            OAuthState.expires_at > datetime.now(timezone.utc),
        )
        .returning(OAuthState.nonce_hash)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
