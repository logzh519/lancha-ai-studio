"""用户与角色管理，挂在 /api/admin 下。

资料字段来自飞书，这里只管「能不能进」和「能看见什么」，不提供编辑姓名头像的入口——
本地改了下次登录就被覆盖，留着只会让人困惑。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth.dependencies import require
from platforms.auth.models import AppUser, Permission, Role, RolePermission, UserIdentity, UserRole, UserSession
from platforms.auth.principal import Principal
from platforms.db import get_session

router = APIRouter()


class RoleIdsPayload(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class ActivePayload(BaseModel):
    is_active: bool


class RoleCreatePayload(BaseModel):
    code: str
    name: str
    description: str = ""
    permission_ids: list[int] = Field(default_factory=list)


class RoleUpdatePayload(BaseModel):
    name: str
    description: str = ""
    permission_ids: list[int] = Field(default_factory=list)


async def _role_ids_by_user(session: AsyncSession) -> dict[int, list[int]]:
    rows = (await session.execute(select(UserRole.user_id, UserRole.role_id))).all()
    grouped: dict[int, list[int]] = {}
    for user_id, role_id in rows:
        grouped.setdefault(user_id, []).append(role_id)
    return grouped


@router.get("/users", dependencies=[Depends(require("platform:user:view"))])
async def list_users(session: AsyncSession = Depends(get_session)):
    """一次返回全部用户。公司内部系统量级有限，真的慢了再加分页。"""
    stmt = (
        select(
            AppUser.id,
            AppUser.username,
            AppUser.display_name,
            AppUser.is_superuser,
            AppUser.is_active,
            UserIdentity.avatar_url,
            UserIdentity.email,
            UserIdentity.last_login_at,
        )
        .outerjoin(UserIdentity, UserIdentity.user_id == AppUser.id)
        .order_by(AppUser.id)
    )
    grouped = await _role_ids_by_user(session)
    return [
        {
            "id": row.id,
            "username": row.username,
            "display_name": row.display_name,
            "avatar_url": row.avatar_url or "",
            "email": row.email or "",
            "superuser": row.is_superuser,
            "is_active": row.is_active,
            "last_login_at": row.last_login_at,
            "role_ids": grouped.get(row.id, []),
        }
        for row in (await session.execute(stmt)).all()
    ]


@router.patch("/users/{user_id}/roles")
async def set_user_roles(
    user_id: int,
    payload: RoleIdsPayload,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require("platform:user:manage")),
):
    user = await session.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在。")

    known = set((await session.execute(select(Role.id).where(Role.id.in_(payload.role_ids)))).scalars())
    unknown = set(payload.role_ids) - known
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"角色不存在：{sorted(unknown)}")

    await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
    for role_id in sorted(known):
        session.add(UserRole(user_id=user_id, role_id=role_id))
    await session.flush()
    return {"id": user_id, "role_ids": sorted(known)}


@router.patch("/users/{user_id}/active")
async def set_user_active(
    user_id: int,
    payload: ActivePayload,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require("platform:user:manage")),
):
    if user_id == principal.user_id and not payload.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能停用自己的账号。")
    user = await session.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在。")

    user.is_active = payload.is_active
    if not payload.is_active:
        # 停用必须立刻生效，否则对方手里的会话还能继续用到过期为止。
        await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
    await session.flush()
    return {"id": user_id, "is_active": user.is_active}


async def _permission_ids_by_role(session: AsyncSession) -> dict[int, list[int]]:
    rows = (await session.execute(select(RolePermission.role_id, RolePermission.permission_id))).all()
    grouped: dict[int, list[int]] = {}
    for role_id, permission_id in rows:
        grouped.setdefault(role_id, []).append(permission_id)
    return grouped


def _role_body(role: Role, permission_ids: list[int], user_count: int) -> dict:
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "permission_ids": sorted(permission_ids),
        "user_count": user_count,
    }


@router.get("/roles", dependencies=[Depends(require("platform:role:view"))])
async def list_roles(session: AsyncSession = Depends(get_session)):
    roles = (await session.execute(select(Role).order_by(Role.id))).scalars().all()
    permissions = await _permission_ids_by_role(session)
    counts: dict[int, int] = {}
    for (role_id,) in (await session.execute(select(UserRole.role_id))).all():
        counts[role_id] = counts.get(role_id, 0) + 1
    return [_role_body(role, permissions.get(role.id, []), counts.get(role.id, 0)) for role in roles]


@router.post("/roles", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require("platform:role:manage"))])
async def create_role(payload: RoleCreatePayload, session: AsyncSession = Depends(get_session)):
    exists = (await session.execute(select(Role.id).where(Role.code == payload.code))).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"角色标识 {payload.code} 已存在。")

    role = Role(code=payload.code, name=payload.name, description=payload.description)
    session.add(role)
    await session.flush()
    await _replace_role_permissions(session, role.id, payload.permission_ids)
    return _role_body(role, payload.permission_ids, 0)


@router.patch("/roles/{role_id}", dependencies=[Depends(require("platform:role:manage"))])
async def update_role(role_id: int, payload: RoleUpdatePayload, session: AsyncSession = Depends(get_session)):
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")

    role.name = payload.name
    role.description = payload.description
    await _replace_role_permissions(session, role_id, payload.permission_ids)
    # 角色可能已有人在用，user_count 不能写死 0，否则前端改完名字人数就显示成 0。
    user_count = (
        await session.execute(select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id))
    ).scalar_one()
    return _role_body(role, payload.permission_ids, user_count)


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require("platform:role:manage"))],
)
async def delete_role(role_id: int, session: AsyncSession = Depends(get_session)):
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")
    # role_permission 与 user_role 的外键是 ON DELETE CASCADE，绑定关系会一并清掉。
    await session.delete(role)
    await session.flush()


async def _replace_role_permissions(session: AsyncSession, role_id: int, permission_ids: list[int]) -> None:
    known = set(
        (await session.execute(select(Permission.id).where(Permission.id.in_(permission_ids)))).scalars()
    )
    unknown = set(permission_ids) - known
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"权限点不存在：{sorted(unknown)}")
    await session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    for permission_id in sorted(known):
        session.add(RolePermission(role_id=role_id, permission_id=permission_id))
    await session.flush()


@router.get("/permissions", dependencies=[Depends(require("platform:role:view"))])
async def list_permissions(session: AsyncSession = Depends(get_session)):
    """按 module 分组返回，前端的勾选框直接照这个结构渲染。"""
    rows = (await session.execute(select(Permission).order_by(Permission.module, Permission.code))).scalars().all()
    grouped: dict[str, list[dict]] = {}
    for permission in rows:
        grouped.setdefault(permission.module, []).append(
            {"id": permission.id, "code": permission.code, "name": permission.name}
        )
    return [{"module": module, "permissions": items} for module, items in grouped.items()]
