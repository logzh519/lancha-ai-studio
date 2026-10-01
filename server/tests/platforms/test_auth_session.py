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
