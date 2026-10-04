import pytest
from httpx import ASGITransport, AsyncClient

from modules.tiktok import service
from modules.tiktok.schemas import ScriptTemplateFields
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

    created = await client.post("/api/tiktok/script-templates", json=PAYLOAD, headers=admin)
    assert created.status_code == 201
    body = created.json()
    assert body["created_by"] == int(admin["X-User-Id"])
    assert body["content"] == PAYLOAD["content"]
    template_id = body["id"]

    listed = (await client.get("/api/tiktok/script-templates", headers=admin)).json()
    assert [t["id"] for t in listed][:1] == [template_id]
    assert "content" not in listed[0]

    updated = await client.put(
        f"/api/tiktok/script-templates/{template_id}",
        json={**PAYLOAD, "status": "test", "version": "1.1.0"},
        headers=admin,
    )
    assert updated.status_code == 200
    assert (updated.json()["status"], updated.json()["version"]) == ("test", "1.1.0")

    detail = await client.get(f"/api/tiktok/script-templates/{template_id}", headers=admin)
    assert detail.json()["version"] == "1.1.0"

    assert (await client.delete(f"/api/tiktok/script-templates/{template_id}", headers=admin)).status_code == 204
    assert (await client.get(f"/api/tiktok/script-templates/{template_id}", headers=admin)).status_code == 404


async def test_requires_permission(client, session):
    plain = await _user(session, "tiktok_plain")
    assert (await client.get("/api/tiktok/script-templates", headers=plain)).status_code == 403
    assert (await client.post("/api/tiktok/script-templates", json=PAYLOAD, headers=plain)).status_code == 403


@pytest.mark.parametrize(
    "override",
    [{"category": "shoes"}, {"status": "draft"}, {"duration_seconds": 0}, {"version": "1.0"}, {"name": ""}],
)
async def test_rejects_invalid_fields(client, session, override):
    admin = await _user(session, "tiktok_admin", superuser=True)
    response = await client.post("/api/tiktok/script-templates", json={**PAYLOAD, **override}, headers=admin)
    assert response.status_code == 422


async def test_create_with_explicit_id_keeps_sequence_ahead(session):
    fields = ScriptTemplateFields(**PAYLOAD)
    explicit = await service.create_script_template(session, fields, created_by=None, template_id=10**6)
    following = await service.create_script_template(session, fields, created_by=None)
    assert following.id > explicit.id
