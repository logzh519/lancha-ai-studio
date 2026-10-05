import pytest
from httpx import ASGITransport, AsyncClient

from modules.tiktok_studio import service
from modules.tiktok_studio.schemas import ProductMasterFields
from platforms.auth.models import AppUser
from platforms.config import Settings
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db

BASE = "/api/tiktok_studio/product-masters"
PAYLOAD = {
    "sku": "LC-T001",
    "asin": "B0TEST0001",
    "color": "黑色",
    "store": "US 旗舰店",
    "pid": "1729000000001",
    "category": "上衣",
    "description": "纯棉短袖",
    "selling_points": "透气\n不起球",
    "main_image_url": "https://example.com/main.jpg",
    "sub_images": ["https://example.com/sub1.jpg", "https://example.com/sub2.jpg"],
    "three_view_images": ["https://example.com/f.jpg", "https://example.com/s.jpg", "https://example.com/b.jpg"],
    "three_view_reference_images": ["https://example.com/ref.jpg"],
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

    created = await client.post(BASE, json=PAYLOAD, headers=admin)
    assert created.status_code == 201
    body = created.json()
    assert body["created_by"] == int(admin["X-User-Id"])
    assert body["three_view_images"] == PAYLOAD["three_view_images"]
    product_id = body["id"]

    listed = (await client.get(BASE, headers=admin)).json()["items"]
    assert [p["id"] for p in listed][:1] == [product_id]
    assert listed[0]["main_image_url"] == PAYLOAD["main_image_url"]
    assert "description" not in listed[0]

    updated = await client.put(f"{BASE}/{product_id}", json={**PAYLOAD, "color": "白色", "sub_images": []}, headers=admin)
    assert updated.status_code == 200
    assert (updated.json()["color"], updated.json()["sub_images"]) == ("白色", [])

    detail = await client.get(f"{BASE}/{product_id}", headers=admin)
    assert detail.json()["color"] == "白色"

    assert (await client.delete(f"{BASE}/{product_id}", headers=admin)).status_code == 204
    assert (await client.get(f"{BASE}/{product_id}", headers=admin)).status_code == 404


async def test_only_sku_is_required(client, session):
    admin = await _user(session, "tiktok_admin", superuser=True)
    response = await client.post(BASE, json={"sku": "LC-T002"}, headers=admin)
    assert response.status_code == 201
    assert response.json()["main_image_url"] is None


async def test_list_filters_by_sku_asin_pid(client, session):
    admin = await _user(session, "tiktok_admin", superuser=True)
    for sku, asin, pid in [("SKU-A", "B0AAA", "P100"), ("SKU-B", "B0BBB", "P200"), ("100%_棉", None, None)]:
        await service.create_product_master(session, ProductMasterFields(sku=sku, asin=asin, pid=pid), None)

    async def skus(keyword: str) -> list[str]:
        response = await client.get(BASE, params={"keyword": keyword}, headers=admin)
        return [p["sku"] for p in response.json()["items"]]

    assert await skus("SKU-A") == ["SKU-A"]
    assert await skus("b0bbb") == ["SKU-B"]
    assert await skus("P100") == ["SKU-A"]
    assert await skus("%_") == ["100%_棉"]


async def test_requires_permission(client, session):
    plain = await _user(session, "tiktok_plain")
    assert (await client.get(BASE, headers=plain)).status_code == 403
    assert (await client.post(BASE, json=PAYLOAD, headers=plain)).status_code == 403


@pytest.mark.parametrize(
    "override",
    [
        {"sku": ""},
        {"three_view_images": ["https://example.com/1.jpg"] * 4},
        {"three_view_reference_images": ["https://example.com/1.jpg"] * 4},
        {"sub_images": [""]},
    ],
)
async def test_rejects_invalid_fields(client, session, override):
    admin = await _user(session, "tiktok_admin", superuser=True)
    response = await client.post(BASE, json={**PAYLOAD, **override}, headers=admin)
    assert response.status_code == 422
