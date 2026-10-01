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
