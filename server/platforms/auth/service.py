"""RBAC 查询与权限点同步。"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth.models import AppUser, Permission, RolePermission, UserRole
from platforms.auth.principal import Principal
from platforms.contract import PermissionDef


async def permission_codes(session: AsyncSession, principal: Principal) -> set[str]:
    """主体拥有的权限码；匿名返回空集，超级用户由调用方短路，不查库。"""
    if principal.user_id is None:
        return set()
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .join(AppUser, AppUser.id == UserRole.user_id)
        .where(UserRole.user_id == principal.user_id, AppUser.is_active.is_(True))
    )
    return set((await session.execute(stmt)).scalars().all())


async def is_superuser(session: AsyncSession, principal: Principal) -> bool:
    if principal.is_superuser:
        return True
    if principal.user_id is None:
        return False
    stmt = select(AppUser.is_superuser).where(AppUser.id == principal.user_id, AppUser.is_active.is_(True))
    return bool((await session.execute(stmt)).scalar_one_or_none())


async def sync_permissions(session: AsyncSession, declared: tuple[PermissionDef, ...]) -> tuple[int, int, int]:
    """把各模块声明的权限点同步到 platform.permission，返回 (新增, 更新, 删除) 条数。

    删除的权限点会连带清掉 role_permission 中的绑定（外键 ON DELETE CASCADE）。
    """
    existing = {p.code: p for p in (await session.execute(select(Permission))).scalars()}
    wanted = {p.code: p for p in declared}

    added = updated = 0
    for code, item in wanted.items():
        module = code.split(":", 1)[0]
        current = existing.get(code)
        if current is None:
            session.add(Permission(code=code, name=item.name, module=module))
            added += 1
        elif (current.name, current.module) != (item.name, module):
            current.name, current.module = item.name, module
            updated += 1

    stale = [code for code in existing if code not in wanted]
    if stale:
        await session.execute(delete(Permission).where(Permission.code.in_(stale)))
    return added, updated, len(stale)
