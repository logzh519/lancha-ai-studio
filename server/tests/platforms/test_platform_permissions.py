"""平台自身的权限码与菜单：必须进同步列表，否则会被 sync_permissions 当成废弃权限清掉。"""

import pytest
from httpx import ASGITransport, AsyncClient

from platforms import registry
from platforms.auth.models import AppUser, Permission, Role, RolePermission, UserRole
from platforms.auth.permissions import PLATFORM_MENUS, PLATFORM_PERMISSIONS
from platforms.contract import ModuleSpec
from platforms.db import get_session
from platforms.gateway.app import create_app
from platforms.gateway.loader import ModuleLoadError, validate_spec


def test_platform_permissions_are_included_in_sync_list():
    synced = {permission.code for permission in registry.all_permissions()}
    assert {permission.code for permission in PLATFORM_PERMISSIONS} <= synced


def test_platform_menu_paths_match_declared_permissions():
    declared = {permission.code for permission in PLATFORM_PERMISSIONS}
    for menu in PLATFORM_MENUS:
        assert menu.permission in declared


def test_module_named_platform_is_rejected():
    spec = ModuleSpec(name="platform", title="冒充平台")
    with pytest.raises(ModuleLoadError, match="platform"):
        validate_spec(spec, "platform")


@pytest.fixture
async def client(session):
    app = create_app()

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _user(session, *, codes: tuple[str, ...] = ()) -> AppUser:
    user = AppUser(username=f"pp{id(session)}{len(codes)}", is_superuser=False, is_active=True)
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


@pytest.mark.db
async def test_user_without_permission_sees_no_platform_menu(client, session):
    user = await _user(session)
    body = (await client.get("/api/platform/modules", headers={"X-User-Id": str(user.id)})).json()
    assert body["platform_menus"] == []


@pytest.mark.db
async def test_user_with_permission_sees_platform_menu(client, session):
    user = await _user(session, codes=("platform:user:view",))
    body = (await client.get("/api/platform/modules", headers={"X-User-Id": str(user.id)})).json()
    assert [menu["path"] for menu in body["platform_menus"]] == ["/platform/users"]
