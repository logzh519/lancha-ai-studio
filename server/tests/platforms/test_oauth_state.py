"""OAuth state 必须是一次性的，且过期即作废——否则回调可被重放。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from platforms.auth import oauth_state
from platforms.auth.models import OAuthState
from platforms.auth.session import hash_token

pytestmark = pytest.mark.db


async def test_state_can_be_consumed_once(session):
    raw, _ = await oauth_state.create(session, timedelta(minutes=10))

    assert await oauth_state.consume(session, raw) is not None
    assert await oauth_state.consume(session, raw) is None


async def test_expired_state_is_rejected(session):
    raw, _ = await oauth_state.create(session, timedelta(seconds=-1))

    assert await oauth_state.consume(session, raw) is None


async def test_unknown_state_is_rejected(session):
    assert await oauth_state.consume(session, "never-issued") is None


async def test_empty_state_is_rejected(session):
    assert await oauth_state.consume(session, "") is None


async def test_nonce_is_stored_hashed_and_returned_on_consume(session):
    raw, nonce = await oauth_state.create(session, timedelta(minutes=10))

    stored = (await session.execute(select(OAuthState))).scalars().one()
    assert stored.nonce_hash == hash_token(nonce)
    assert await oauth_state.consume(session, raw) == hash_token(nonce)


async def test_each_state_gets_its_own_nonce(session):
    _, first = await oauth_state.create(session, timedelta(minutes=10))
    _, second = await oauth_state.create(session, timedelta(minutes=10))

    assert first != second


async def test_create_sweeps_expired_rows(session):
    session.add(
        OAuthState(
            state_hash="e" * 64,
            nonce_hash="n" * 64,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    await session.flush()

    await oauth_state.create(session, timedelta(minutes=10))

    assert "e" * 64 not in set((await session.execute(select(OAuthState.state_hash))).scalars())
