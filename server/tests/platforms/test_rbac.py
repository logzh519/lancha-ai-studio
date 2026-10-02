"""RBAC：权限点同步、权限查询，以及接口级校验的端到端行为。"""

import pytest
from httpx import ASGITransport, AsyncClient

from platforms.auth import service
from platforms.auth.models import AppUser, Permission, Role, RolePermission, UserRole
from platforms.auth.principal import ANONYMOUS, Principal
from platforms.config import Settings
from platforms.contract import PermissionDef
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db


async def _make_user(session, *, superuser: bool = False, codes: tuple[str, ...] = ()) -> AppUser:
    user = AppUser(username=f"u{id(session)}{len(codes)}{superuser}", is_superuser=superuser, is_active=True)
    session.add(user)
    await session.flush()
    if codes:
        role = Role(code=f"r{user.id}", name="测试角色")
        session.add(role)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        for code in codes:
            permission = Permission(code=code, name=code, module=code.split(":", 1)[0])
            session.add(permission)
            await session.flush()
            session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await session.flush()
    return user


async def test_anonymous_has_no_permission(session):
    assert await service.permission_codes(session, ANONYMOUS) == set()
    assert await service.is_superuser(session, ANONYMOUS) is False


async def test_permission_codes_follow_role_binding(session):
    user = await _make_user(session, codes=("example:item:view",))
    assert await service.permission_codes(session, Principal(user_id=user.id)) == {"example:item:view"}


async def test_inactive_user_loses_permissions(session):
    user = await _make_user(session, codes=("example:item:view",))
    user.is_active = False
    await session.flush()
    assert await service.permission_codes(session, Principal(user_id=user.id)) == set()


async def test_superuser_flag_is_read_from_database(session):
    user = await _make_user(session, superuser=True)
    assert await service.is_superuser(session, Principal(user_id=user.id)) is True


async def test_sync_permissions_adds_updates_and_removes(session):
    added, updated, removed = await service.sync_permissions(
        session, (PermissionDef("example:item:view", "查看条目"),)
    )
    assert (added, updated, removed) == (1, 0, 0)

    added, updated, removed = await service.sync_permissions(
        session, (PermissionDef("example:item:view", "查看条目（改名）"),)
    )
    assert (added, updated, removed) == (0, 1, 0)

    added, updated, removed = await service.sync_permissions(session, ())
    assert (added, updated, removed) == (0, 0, 1)


@pytest.fixture
async def client(session):
    app = create_app(Settings(auth_mode="dev_header"))

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_request_without_permission_is_rejected(client, session):
    user = await _make_user(session)
    response = await client.get("/api/example/items", headers={"X-User-Id": str(user.id)})
    assert response.status_code == 403
    assert "example:item:view" in response.json()["message"]


async def test_request_with_permission_passes(client, session):
    user = await _make_user(session, codes=("example:item:view",))
    response = await client.get("/api/example/items", headers={"X-User-Id": str(user.id)})
    assert response.status_code == 200


async def test_menus_are_filtered_by_permission(client, session):
    plain = await _make_user(session)
    response = await client.get("/api/modules", headers={"X-User-Id": str(plain.id)})
    assert response.json()["modules"][0]["menus"] == []

    granted = await _make_user(session, codes=("example:item:view",))
    response = await client.get("/api/modules", headers={"X-User-Id": str(granted.id)})
    menus = response.json()["modules"][0]["menus"]
    assert [menu["path"] for menu in menus] == ["/example/items"]
