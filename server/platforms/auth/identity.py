"""外部身份到 app_user 的映射。

与登录方式无关：飞书、公司账号系统都把自己的用户资料归一成 ExternalProfile 后交给这里。
认人顺序是「身份 → 邮箱 → 新建」，中间那步是为了同一个人用不同登录方式进来时能合并到一个账号。
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth.models import AppUser, UserIdentity


@dataclass(frozen=True)
class ExternalProfile:
    provider: str
    external_id: str
    union_id: str = ""
    email: str = ""
    display_name: str = ""
    avatar_url: str = ""


def _normalise_email(email: str) -> str:
    return email.strip().lower()


async def upsert(session: AsyncSession, profile: ExternalProfile) -> AppUser:
    """按外部身份找到或创建 app_user，并刷新身份记录。新用户不授予任何角色。"""
    email = _normalise_email(profile.email)

    identity = (
        await session.execute(
            select(UserIdentity).where(
                UserIdentity.provider == profile.provider,
                UserIdentity.external_id == profile.external_id,
            )
        )
    ).scalar_one_or_none()

    if identity is not None:
        user = await session.get(AppUser, identity.user_id)
    else:
        username = email or f"{profile.provider}_{profile.external_id}"
        user = (
            await session.execute(select(AppUser).where(AppUser.username == username))
        ).scalar_one_or_none()
        if user is None:
            user = AppUser(username=username, display_name=profile.display_name, is_superuser=False, is_active=True)
            session.add(user)
            await session.flush()
        identity = UserIdentity(
            user_id=user.id, provider=profile.provider, external_id=profile.external_id
        )
        session.add(identity)

    # 资料以飞书为准，但 username 一旦确定就不再改——改了会撞唯一约束，也会让审计记录断链。
    if profile.display_name:
        user.display_name = profile.display_name
    identity.union_id = profile.union_id
    identity.email = email
    identity.avatar_url = profile.avatar_url
    identity.last_login_at = datetime.now(timezone.utc)
    await session.flush()
    return user
