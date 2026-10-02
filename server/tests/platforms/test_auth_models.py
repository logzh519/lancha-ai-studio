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
    session.add(OAuthState(state_hash="s" * 64, nonce_hash="n" * 64, expires_at=expires))
    await session.flush()

    session.add(OAuthState(state_hash="s" * 64, nonce_hash="n" * 64, expires_at=expires))
    with pytest.raises(IntegrityError):
        await session.flush()
