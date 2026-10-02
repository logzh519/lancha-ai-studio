"""用户与角色管理：权限闸门、角色分配生效、以及不许把自己锁在门外。"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from platforms.auth.models import (
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
    UserSession,
)
from platforms.config import Settings
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db


@pytest.fixture
async def client(session):
    app = create_app(Settings(auth_mode="dev_header"))

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _user(session, username: str, *, superuser: bool = False) -> AppUser:
    user = AppUser(username=username, display_name=username, is_superuser=superuser, is_active=True)
    session.add(user)
    await session.flush()
    return user


async def _role(session, code: str) -> Role:
    role = Role(code=code, name=code, description="")
    session.add(role)
    await session.flush()
    return role


def _as(user: AppUser) -> dict:
    return {"X-User-Id": str(user.id)}


async def test_user_list_requires_permission(client, session):
    plain = await _user(session, "plain")
    assert (await client.get("/api/admin/users", headers=_as(plain))).status_code == 403


async def test_superuser_can_list_users(client, session):
    admin = await _user(session, "admin", superuser=True)
    body = (await client.get("/api/admin/users", headers=_as(admin))).json()
    assert any(item["username"] == "admin" for item in body)


async def test_assigning_role_grants_permission_codes(client, session):
    admin = await _user(session, "admin2", superuser=True)
    target = await _user(session, "target")
    role = await _role(session, "ops")
    permission = Permission(code="example:item:view", name="查看条目", module="example")
    session.add(permission)
    await session.flush()
    session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await session.flush()

    response = await client.patch(
        f"/api/admin/users/{target.id}/roles", json={"role_ids": [role.id]}, headers=_as(admin)
    )

    assert response.status_code == 200
    modules = (await client.get("/api/modules", headers=_as(target))).json()
    assert "example:item:view" in modules["permissions"]


async def test_cannot_deactivate_self(client, session):
    admin = await _user(session, "admin3", superuser=True)
    response = await client.patch(
        f"/api/admin/users/{admin.id}/active", json={"is_active": False}, headers=_as(admin)
    )
    assert response.status_code == 400


async def test_deactivated_user_loses_access(client, session):
    admin = await _user(session, "admin4", superuser=True)
    target = await _user(session, "target4")
    role = await _role(session, "user_viewer4")
    permission = Permission(code="platform:user:view", name="查看用户", module="platform")
    session.add(permission)
    await session.flush()
    session.add_all(
        [
            RolePermission(role_id=role.id, permission_id=permission.id),
            UserRole(user_id=target.id, role_id=role.id),
        ]
    )
    await session.flush()

    # 停用前必须有权限，否则 403 与是否停用无关，测不出差异
    assert (await client.get("/api/admin/users", headers=_as(target))).status_code == 200

    await client.patch(f"/api/admin/users/{target.id}/active", json={"is_active": False}, headers=_as(admin))

    assert (await client.get("/api/admin/users", headers=_as(target))).status_code == 403


async def test_role_crud_round_trip(client, session):
    admin = await _user(session, "admin5", superuser=True)
    permission = Permission(code="example:item:create", name="创建条目", module="example")
    session.add(permission)
    await session.flush()

    created = await client.post(
        "/api/admin/roles",
        json={"code": "editor", "name": "编辑", "description": "", "permission_ids": [permission.id]},
        headers=_as(admin),
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    listed = (await client.get("/api/admin/roles", headers=_as(admin))).json()
    assert [role for role in listed if role["id"] == role_id][0]["permission_ids"] == [permission.id]

    updated = await client.patch(
        f"/api/admin/roles/{role_id}",
        json={"name": "编辑（改名）", "description": "", "permission_ids": []},
        headers=_as(admin),
    )
    assert updated.json()["name"] == "编辑（改名）"
    assert updated.json()["permission_ids"] == []

    assert (await client.delete(f"/api/admin/roles/{role_id}", headers=_as(admin))).status_code == 204
    assert all(role["id"] != role_id for role in (await client.get("/api/admin/roles", headers=_as(admin))).json())


async def test_duplicate_role_code_is_rejected(client, session):
    admin = await _user(session, "admin6", superuser=True)
    await _role(session, "dup")

    response = await client.post(
        "/api/admin/roles",
        json={"code": "dup", "name": "重复", "description": "", "permission_ids": []},
        headers=_as(admin),
    )
    assert response.status_code == 409


async def test_permission_list_is_grouped_by_module(client, session):
    admin = await _user(session, "admin7", superuser=True)
    session.add(Permission(code="example:item:view", name="查看条目", module="example"))
    await session.flush()

    body = (await client.get("/api/admin/permissions", headers=_as(admin))).json()

    assert any(group["module"] == "example" for group in body)


async def test_deleting_role_removes_user_binding(client, session):
    admin = await _user(session, "admin8", superuser=True)
    target = await _user(session, "target8")
    role = await _role(session, "temp")
    session.add(UserRole(user_id=target.id, role_id=role.id))
    await session.flush()

    await client.delete(f"/api/admin/roles/{role.id}", headers=_as(admin))

    users = (await client.get("/api/admin/users", headers=_as(admin))).json()
    assert [u for u in users if u["id"] == target.id][0]["role_ids"] == []


async def test_deactivating_user_deletes_their_sessions(client, session):
    admin = await _user(session, "admin9", superuser=True)
    target = await _user(session, "target9")
    other = await _user(session, "other9")
    expires = datetime.now(UTC) + timedelta(days=1)
    session.add_all(
        [
            UserSession(token_hash="a" * 64, user_id=target.id, expires_at=expires),
            UserSession(token_hash="b" * 64, user_id=other.id, expires_at=expires),
        ]
    )
    await session.flush()

    await client.patch(f"/api/admin/users/{target.id}/active", json={"is_active": False}, headers=_as(admin))

    remaining = set((await session.execute(select(UserSession.user_id))).scalars())
    assert target.id not in remaining
    assert other.id in remaining


async def test_write_endpoints_require_manage_permission(client, session):
    plain = await _user(session, "plain10")
    target = await _user(session, "target10")
    role = await _role(session, "r10")
    calls = [
        ("PATCH", f"/api/admin/users/{target.id}/roles", {"role_ids": []}),
        ("PATCH", f"/api/admin/users/{target.id}/active", {"is_active": False}),
        ("POST", "/api/admin/roles", {"code": "x10", "name": "x", "permission_ids": []}),
        ("PATCH", f"/api/admin/roles/{role.id}", {"name": "x", "permission_ids": []}),
        ("DELETE", f"/api/admin/roles/{role.id}", None),
    ]
    for method, url, body in calls:
        response = await client.request(method, url, json=body, headers=_as(plain))
        assert response.status_code == 403, (method, url)


async def test_unknown_references_are_rejected(client, session):
    admin = await _user(session, "admin11", superuser=True)
    target = await _user(session, "target11")

    assert (
        await client.patch(f"/api/admin/users/{target.id}/roles", json={"role_ids": [999999]}, headers=_as(admin))
    ).status_code == 400
    assert (
        await client.patch("/api/admin/users/999999/roles", json={"role_ids": []}, headers=_as(admin))
    ).status_code == 404
    assert (
        await client.patch("/api/admin/users/999999/active", json={"is_active": False}, headers=_as(admin))
    ).status_code == 404
    assert (
        await client.post(
            "/api/admin/roles",
            json={"code": "bad11", "name": "x", "permission_ids": [999999]},
            headers=_as(admin),
        )
    ).status_code == 400
    assert (await client.delete("/api/admin/roles/999999", headers=_as(admin))).status_code == 404


async def test_update_role_keeps_user_count(client, session):
    admin = await _user(session, "admin12", superuser=True)
    target = await _user(session, "target12")
    role = await _role(session, "r12")
    session.add(UserRole(user_id=target.id, role_id=role.id))
    await session.flush()

    updated = await client.patch(
        f"/api/admin/roles/{role.id}", json={"name": "改名", "permission_ids": []}, headers=_as(admin)
    )

    assert updated.json()["user_count"] == 1
