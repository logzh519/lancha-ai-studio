"""请求之外的数据库会话：正常结束提交，抛异常回滚。"""

from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from platforms.auth.models import Role
from platforms.db import session_scope

pytestmark = pytest.mark.db


async def test_session_scope_commits_on_success(db_ready):
    code = f"scope_{uuid4().hex[:12]}"
    async with session_scope() as session:
        session.add(Role(code=code, name="提交"))

    async with session_scope() as session:
        assert await session.scalar(select(Role).where(Role.code == code)) is not None
        await session.execute(delete(Role).where(Role.code == code))


async def test_session_scope_rolls_back_on_error(db_ready):
    code = f"scope_{uuid4().hex[:12]}"
    with pytest.raises(RuntimeError):
        async with session_scope() as session:
            session.add(Role(code=code, name="回滚"))
            await session.flush()
            raise RuntimeError("中断")

    async with session_scope() as session:
        assert await session.scalar(select(Role).where(Role.code == code)) is None
