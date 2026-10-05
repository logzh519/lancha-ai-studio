from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from modules.tiktok_studio import service
from modules.tiktok_studio.models import Batch, Task
from platforms.auth.models import AppUser
from platforms.config import Settings
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db

PREVIEW_URL = "/api/tiktok_studio/orders/preview"
BATCH_URL = "/api/tiktok_studio/batches"


@pytest.fixture
async def client(session):
    app = create_app(Settings(auth_mode="dev_header"))

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


async def _user(session, username: str, *, superuser: bool = False) -> dict[str, str]:
    user = AppUser(username=username, display_name=username, is_superuser=superuser, is_active=True)
    session.add(user)
    await session.flush()
    return {"X-User-Id": str(user.id)}


async def _valid_items(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    response = await client.post(PREVIEW_URL, json={"skus": ["WTK9167"]}, headers=headers)
    assert response.status_code == 200, response.text
    items = [item for item in response.json()["items"] if item["asin"]]
    assert items
    return items[:2]


def _batch_payload(items: list[dict], request_id: str | None = None) -> dict:
    return {
        "request_id": request_id or str(uuid4()),
        "name": "端到端建单测试",
        "pipeline_key": "video_gen_15s",
        "items": [{key: item[key] for key in ("sku", "asin", "color", "shop")} for item in items],
        "note": "API 流程",
    }


async def test_preview_create_and_idempotent_replay(client, session):
    headers = await _user(session, "task_creator", superuser=True)
    items = await _valid_items(client, headers)
    payload = _batch_payload(items)

    created = await client.post(BATCH_URL, json=payload, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["total_tasks"] == len(items)

    batch_list = await client.get(BATCH_URL, headers=headers)
    assert batch_list.status_code == 200
    assert batch_list.json()["total"] == 1
    assert batch_list.json()["items"][0]["id"] == body["id"]
    task_list = await client.get(f"{BATCH_URL}/{body['id']}/tasks", headers=headers)
    assert task_list.status_code == 200
    assert task_list.json()["total"] == len(items)
    assert {task["biz_key"] for task in task_list.json()["items"]} == {item["asin"] for item in items}

    replay = await client.post(BATCH_URL, json=payload, headers=headers)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == body["id"]

    batch_count = await session.scalar(select(func.count()).select_from(Batch))
    task_count = await session.scalar(select(func.count()).select_from(Task))
    tasks = list((await session.execute(select(Task).where(Task.batch_id == body["id"]))).scalars())
    assert batch_count == 1
    assert task_count == len(items)
    assert all(task.status == "admitted_pending" for task in tasks)
    assert all(task.context == {key: item[key] for key in ("sku", "asin", "color", "shop")} for task, item in zip(tasks, items))


async def test_request_id_cannot_be_reused_for_different_content(client, session):
    headers = await _user(session, "task_idempotency", superuser=True)
    items = await _valid_items(client, headers)
    payload = _batch_payload(items)
    assert (await client.post(BATCH_URL, json=payload, headers=headers)).status_code == 201

    changed = {**payload, "name": "不同内容"}
    response = await client.post(BATCH_URL, json=changed, headers=headers)
    assert response.status_code == 409


async def test_create_rejects_forged_mapping_and_duplicate_asins(client, session):
    headers = await _user(session, "task_validation", superuser=True)
    item = (await _valid_items(client, headers))[0]
    changed_item = {**item, "color": "伪造颜色"}
    response = await client.post(BATCH_URL, json=_batch_payload([changed_item]), headers=headers)
    assert response.status_code == 422

    duplicate_payload = _batch_payload([item, item])
    duplicate = await client.post(BATCH_URL, json=duplicate_payload, headers=headers)
    assert duplicate.status_code == 422


async def test_preview_unknown_sku_is_explained_and_empty_mapping_is_not_creatable(client, session):
    headers = await _user(session, "task_unknown", superuser=True)
    response = await client.post(PREVIEW_URL, json={"skus": ["NO-SUCH-SKU"]}, headers=headers)
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["asin"] is None
    assert "未找到 ASIN" in item["warnings"]


async def test_preview_keeps_other_skus_when_one_lookup_fails(client, session, monkeypatch):
    headers = await _user(session, "task_partial_preview", superuser=True)

    async def lookup(_session, sku):
        if sku == "BROKEN":
            raise service.InvalidTaskOrder("产品库暂时不可用")
        return [{"sku": sku, "asin": "B0VALID0001", "color": "蓝色", "store": "US-02"}]

    monkeypatch.setattr(service, "_lookup_sku", lookup)
    response = await client.post(PREVIEW_URL, json={"skus": ["BROKEN", "GOOD"]}, headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["asin"] is None
    assert items[0]["warnings"] == ["产品库暂时不可用"]
    assert items[1]["asin"] == "B0VALID0001"


async def test_task_creation_endpoints_require_permission(client, session):
    headers = await _user(session, "task_no_permission")
    preview = await client.post(PREVIEW_URL, json={"skus": ["WTK9167"]}, headers=headers)
    create = await client.post(BATCH_URL, json=_batch_payload([{
        "sku": "WTK9167", "asin": "B000000000", "color": None, "shop": None,
    }]), headers=headers)
    assert preview.status_code == 403
    assert create.status_code == 403
    assert (await client.get(BATCH_URL, headers=headers)).status_code == 403


async def test_batch_and_task_reads_are_limited_to_the_owner(client, session):
    owner = await _user(session, "task_owner", superuser=True)
    outsider = await _user(session, "task_outsider", superuser=True)
    items = await _valid_items(client, owner)
    created = await client.post(BATCH_URL, json=_batch_payload(items), headers=owner)
    batch_id = created.json()["id"]

    assert (await client.get(BATCH_URL, headers=outsider)).json()["total"] == 0
    assert (await client.get(f"{BATCH_URL}/{batch_id}/tasks", headers=outsider)).status_code == 404
