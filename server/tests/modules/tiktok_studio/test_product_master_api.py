from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from modules.tiktok_studio import service
from modules.tiktok_studio.models import ProductMaster
from modules.tiktok_studio.schemas import ProductMasterFields
from platforms.auth.models import AppUser
from platforms.config import Settings
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db

BASE = "/api/tiktok_studio/product-masters"


def ext(name: str) -> dict:
    return {"key": None, "url": f"https://example.com/{name}.jpg", "type": "external"}


def tos(key: str) -> dict:
    return {"key": key, "url": f"https://cdn.test/{key}", "type": "tos"}


PAYLOAD = {
    "sku": "LC-T001",
    "asin": "B0TEST0001",
    "color": "黑色",
    "store": "US 旗舰店",
    "pid": "1729000000001",
    "category": "上衣",
    "description": "纯棉短袖",
    "selling_points": "透气\n不起球",
    "main_image": ext("main"),
    "sub_images": [ext("sub1"), ext("sub2")],
    "three_view_images": [ext("three_view")],
    "three_view_reference_images": [ext("main"), ext("sub1")],
}


class FakeStorage:
    """记录 get_storage(type) 后的上传与删除调用；key 以 fail 开头时模拟删除失败。缺省存储类型为 tos。"""

    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []
        self.uploaded: list[tuple[str, bytes]] = []

    def get(self, provider: str = "tos"):
        storage = self

        class _Storage:
            type = provider

            def upload(self, key: str, data: bytes):
                storage.uploaded.append((key, data))
                return SimpleNamespace(url=f"https://cdn.test/{key}")

            def delete_file(self, key: str) -> None:
                if key.startswith("fail"):
                    raise RuntimeError("boom")
                storage.deleted.append((provider, key))

        return _Storage()


@pytest.fixture
def storage(monkeypatch) -> FakeStorage:
    fake = FakeStorage()
    monkeypatch.setattr(service, "get_storage", fake.get)
    return fake


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


async def test_crud_flow(client, session, storage):
    admin = await _user(session, "tiktok_admin", superuser=True)

    created = await client.post(BASE, json=PAYLOAD, headers=admin)
    assert created.status_code == 201
    body = created.json()
    assert body["created_by"] == int(admin["X-User-Id"])
    assert body["three_view_images"] == PAYLOAD["three_view_images"]
    product_id = body["id"]

    listed = (await client.get(BASE, headers=admin)).json()["items"]
    assert [p["id"] for p in listed][:1] == [product_id]
    assert listed[0]["main_image"] == PAYLOAD["main_image"]
    assert "description" not in listed[0]

    changes = {"color": "白色", "sub_images": [], "three_view_reference_images": [ext("main")]}
    updated = await client.put(f"{BASE}/{product_id}", json={**PAYLOAD, **changes}, headers=admin)
    assert updated.status_code == 200
    assert (updated.json()["color"], updated.json()["sub_images"]) == ("白色", [])

    detail = await client.get(f"{BASE}/{product_id}", headers=admin)
    assert detail.json()["color"] == "白色"

    assert (await client.delete(f"{BASE}/{product_id}", headers=admin)).status_code == 204
    assert (await client.get(f"{BASE}/{product_id}", headers=admin)).status_code == 404
    assert storage.deleted == []    # 外部链接不清理


async def test_only_sku_is_required(client, session):
    admin = await _user(session, "tiktok_admin", superuser=True)
    response = await client.post(BASE, json={"sku": "LC-T002"}, headers=admin)
    assert response.status_code == 201
    assert response.json()["main_image"] is None


async def _stored_product(session, sku: str, **images) -> ProductMaster:
    product = ProductMaster(sku=sku, **images)
    session.add(product)
    await session.flush()
    return product


async def test_delete_purges_stored_objects(client, session, storage):
    admin = await _user(session, "tiktok_admin", superuser=True)
    product = await _stored_product(
        session, "DEL-1",
        main_image=tos("amazon/B0X/01_MAIN.jpg"),
        sub_images=[tos("amazon/B0X/02_PT01.jpg"), ext("outside")],
        three_view_reference_images=[tos("amazon/B0X/01_MAIN.jpg")],
        three_view_images=[{"key": "three_view/B0X/a.png", "url": None, "type": "obs"}],
    )

    assert (await client.delete(f"{BASE}/{product.id}", headers=admin)).status_code == 204

    assert sorted(storage.deleted) == [
        ("obs", "three_view/B0X/a.png"), ("tos", "amazon/B0X/01_MAIN.jpg"), ("tos", "amazon/B0X/02_PT01.jpg"),
    ]


async def test_update_purges_removed_objects_and_rejects_unknown_ones(client, session, storage):
    admin = await _user(session, "tiktok_admin", superuser=True)
    product = await _stored_product(
        session, "UPD-1", main_image=tos("amazon/B0Y/01_MAIN.jpg"), sub_images=[tos("amazon/B0Y/02_PT01.jpg")],
    )
    fields = {"sku": "UPD-1", "main_image": tos("amazon/B0Y/01_MAIN.jpg")}

    forged = await client.put(f"{BASE}/{product.id}", json={**fields, "sub_images": [tos("other/secret.jpg")]}, headers=admin)
    assert forged.status_code == 422
    assert storage.deleted == []

    updated = await client.put(f"{BASE}/{product.id}", json={**fields, "sub_images": [ext("new")]}, headers=admin)
    assert updated.status_code == 200
    assert updated.json()["sub_images"] == [ext("new")]
    assert storage.deleted == [("tos", "amazon/B0Y/02_PT01.jpg")]


async def test_upload_image_persists_to_product(client, session, storage):
    admin = await _user(session, "tiktok_admin", superuser=True)
    product = await _stored_product(
        session, "UP-1", main_image=tos("amazon/B0U/01_MAIN.jpg"), sub_images=[ext("old")],
        three_view_images=[tos("amazon/B0U/THREE_VIEW.png")],
    )
    png = {**admin, "Content-Type": "image/png"}

    sub = await client.post(f"{BASE}/{product.id}/images/sub_images", content=b"sub", headers=png)
    assert sub.status_code == 201
    key = sub.json()["key"]
    assert key.startswith(f"tiktok_studio/product_masters/{product.id}/") and key.endswith(".png")
    assert sub.json() == tos(key)

    main = await client.post(f"{BASE}/{product.id}/images/main_image", content=b"main", headers=png)
    assert main.status_code == 201
    three_view = await client.post(f"{BASE}/{product.id}/images/three_view_images", content=b"tv", headers=png)
    assert three_view.status_code == 201
    assert [data for _, data in storage.uploaded] == [b"sub", b"main", b"tv"]
    assert storage.deleted == [("tos", "amazon/B0U/01_MAIN.jpg"), ("tos", "amazon/B0U/THREE_VIEW.png")]

    detail = (await client.get(f"{BASE}/{product.id}", headers=admin)).json()
    assert detail["main_image"] == main.json()
    assert detail["sub_images"] == [ext("old"), sub.json()]
    assert detail["three_view_images"] == [three_view.json()]    # 三视图只有一张，上传即替换

    saved = await client.put(f"{BASE}/{product.id}", json={"sku": "UP-1", "sub_images": [sub.json()]}, headers=admin)
    assert saved.status_code == 200


async def test_upload_image_rejects_invalid_requests(client, session, storage):
    admin = await _user(session, "tiktok_admin", superuser=True)
    product = await _stored_product(session, "UP-2")
    url = f"{BASE}/{product.id}/images"
    png = {**admin, "Content-Type": "image/png"}

    assert (await client.post(f"{url}/sub_images", content=b"x", headers={**admin, "Content-Type": "text/plain"})).status_code == 415
    assert (await client.post(f"{url}/sub_images", content=b"", headers=png)).status_code == 422
    assert (await client.post(f"{url}/sku", content=b"x", headers=png)).status_code == 422
    assert (await client.post(f"{url}/three_view_reference_images", content=b"x", headers=png)).status_code == 422
    assert (await client.post(f"{BASE}/999999/images/sub_images", content=b"x", headers=png)).status_code == 404
    assert storage.uploaded == []


async def test_regenerate_three_view(client, session):
    admin = await _user(session, "tiktok_admin", superuser=True)
    product = await _stored_product(
        session, "GEN-1", view_status="done", gen_status="failed", gen_error="boom",
        import_trace={"gen": {"input": {}, "output": {}, "error_code": None, "error_message": "boom"}},
    )
    url = f"{BASE}/{product.id}/regenerate-three-view"

    response = await client.post(url, headers=admin)
    assert response.status_code == 200
    body = response.json()
    assert (body["gen_status"], body["gen_error"], body["import_trace"]) == ("pending", None, {})

    assert (await client.post(url, headers=admin)).status_code == 409    # 生成中不能重复提交
    pending_view = await _stored_product(session, "GEN-2", view_status="pending")
    assert (await client.post(f"{BASE}/{pending_view.id}/regenerate-three-view", headers=admin)).status_code == 409


async def test_create_rejects_stored_objects(client, session):
    admin = await _user(session, "tiktok_admin", superuser=True)
    response = await client.post(BASE, json={"sku": "NEW-1", "main_image": tos("amazon/B0Z/01.jpg")}, headers=admin)
    assert response.status_code == 422


async def test_purge_failure_is_logged_not_raised(storage, caplog):
    await service.purge_objects([service.StoredRef("tos", "fail.jpg"), service.StoredRef("tos", "ok.jpg")])
    assert storage.deleted == [("tos", "ok.jpg")]
    assert "fail.jpg" in caplog.text


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
        {"three_view_images": [ext("1"), ext("2")]},
        {"three_view_reference_images": [ext("main")] * 4},
        {"three_view_reference_images": [ext("elsewhere")]},
        {"sub_images": [], "three_view_reference_images": [ext("sub1")]},
        {"sub_images": [{"key": None, "url": "", "type": "external"}]},
        {"sub_images": [{"key": "a.jpg", "url": "https://example.com/a.jpg", "type": "external"}]},
        {"main_image": {"key": None, "url": "https://example.com/a.jpg", "type": "tos"}},
    ],
)
async def test_rejects_invalid_fields(client, session, override):
    admin = await _user(session, "tiktok_admin", superuser=True)
    response = await client.post(BASE, json={**PAYLOAD, **override}, headers=admin)
    assert response.status_code == 422
