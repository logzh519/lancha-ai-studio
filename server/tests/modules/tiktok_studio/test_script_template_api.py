import pytest
from httpx import ASGITransport, AsyncClient

from modules.tiktok_studio import service
from modules.tiktok_studio.schemas import ScriptTemplateFields
from platforms.auth.models import AppUser
from platforms.config import Settings
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db

PAYLOAD = {
    "name": "开袋试穿",
    "category": "top",
    "duration_seconds": 15,
    "content": "# 脚本\n正文",
    "status": "formal",
    "version": "1.0.0",
    "reference_video_url": "https://example.com/v.mp4",
}


@pytest.fixture
async def client(session):
    app = create_app(Settings(auth_mode="dev_header"))

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _user(session, username: str, *, superuser: bool = False) -> dict:
    user = AppUser(username=username, display_name=username, is_superuser=superuser, is_active=True)
    session.add(user)
    await session.flush()
    return {"X-User-Id": str(user.id)}


async def test_crud_flow(client, session):
    admin = await _user(session, "tiktok_admin", superuser=True)

    created = await client.post("/api/tiktok_studio/script-templates", json=PAYLOAD, headers=admin)
    assert created.status_code == 201
    body = created.json()
    assert body["created_by"] == int(admin["X-User-Id"])
    assert body["content"] == PAYLOAD["content"]
    template_id = body["id"]

    listed = (await client.get("/api/tiktok_studio/script-templates", headers=admin)).json()["items"]
    assert [t["id"] for t in listed][:1] == [template_id]
    assert "content" not in listed[0]

    updated = await client.put(
        f"/api/tiktok_studio/script-templates/{template_id}",
        json={**PAYLOAD, "status": "test", "version": "1.1.0"},
        headers=admin,
    )
    assert updated.status_code == 200
    assert (updated.json()["status"], updated.json()["version"]) == ("test", "1.1.0")

    detail = await client.get(f"/api/tiktok_studio/script-templates/{template_id}", headers=admin)
    assert detail.json()["version"] == "1.1.0"

    assert (await client.delete(f"/api/tiktok_studio/script-templates/{template_id}", headers=admin)).status_code == 204
    assert (await client.get(f"/api/tiktok_studio/script-templates/{template_id}", headers=admin)).status_code == 404


async def test_list_is_paginated(client, session):
    admin = await _user(session, "tiktok_admin", superuser=True)
    fields = ScriptTemplateFields(**PAYLOAD)
    created = [(await service.create_script_template(session, fields, created_by=None)).id for _ in range(3)]

    first = (await client.get("/api/tiktok_studio/script-templates?page=1&page_size=2", headers=admin)).json()
    second = (await client.get("/api/tiktok_studio/script-templates?page=2&page_size=2", headers=admin)).json()
    assert first["total"] == second["total"] >= 3
    assert [t["id"] for t in first["items"]] == created[::-1][:2]
    assert second["items"][0]["id"] == created[0]
    assert (await client.get("/api/tiktok_studio/script-templates?page_size=101", headers=admin)).status_code == 422


async def test_list_filters_by_name_keyword(client, session):
    admin = await _user(session, "tiktok_admin", superuser=True)
    for name in ["夏季上衣开袋", "冬季外套试穿", "100%_纯棉"]:
        await service.create_script_template(session, ScriptTemplateFields(**{**PAYLOAD, "name": name}), None)

    async def names(keyword: str) -> list[str]:
        response = await client.get("/api/tiktok_studio/script-templates", params={"keyword": keyword}, headers=admin)
        return [t["name"] for t in response.json()["items"]]

    assert await names("开袋") == ["夏季上衣开袋"]
    assert await names("%_") == ["100%_纯棉"]
    assert "冬季外套试穿" not in await names("夏季")


async def test_requires_permission(client, session):
    plain = await _user(session, "tiktok_plain")
    assert (await client.get("/api/tiktok_studio/script-templates", headers=plain)).status_code == 403
    assert (await client.post("/api/tiktok_studio/script-templates", json=PAYLOAD, headers=plain)).status_code == 403


@pytest.mark.parametrize(
    "override",
    [{"category": "shoes"}, {"status": "draft"}, {"duration_seconds": 0}, {"version": "1.0"}, {"name": ""}],
)
async def test_rejects_invalid_fields(client, session, override):
    admin = await _user(session, "tiktok_admin", superuser=True)
    response = await client.post("/api/tiktok_studio/script-templates", json={**PAYLOAD, **override}, headers=admin)
    assert response.status_code == 422


async def test_create_with_explicit_id_keeps_sequence_ahead(session):
    fields = ScriptTemplateFields(**PAYLOAD)
    explicit = await service.create_script_template(session, fields, created_by=None, template_id=10**6)
    following = await service.create_script_template(session, fields, created_by=None)
    assert following.id > explicit.id
