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
