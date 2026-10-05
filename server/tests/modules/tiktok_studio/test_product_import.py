"""按货号批量导入：同步入库与去重、失败阶段重试，以及 worker 的抓取、参考图、三视图三个后台阶段。"""

import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from modules.tiktok_studio import service, worker
from modules.tiktok_studio.models import ProductMaster
from modules.tiktok_studio.module import MODULE
from platforms.auth.models import AppUser
from platforms.config import Settings
from platforms.contract import LoopContext
from platforms.db import get_session, session_scope
from platforms.gateway.app import create_app
from platforms.tools import ToolResult

pytestmark = pytest.mark.db

BASE = "/api/tiktok_studio/product-masters"
WTK9167_RECORDS = 10    # mock 数据集中 WTK9167 的 SKU 记录数


@pytest.fixture
async def client(session):
    app = create_app(Settings(auth_mode="dev_header"))

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def admin(session) -> dict:
    user = AppUser(username="import_admin", display_name="import_admin", is_superuser=True, is_active=True)
    session.add(user)
    await session.flush()
    return {"X-User-Id": str(user.id)}


def test_module_declares_singleton_import_loops():
    assert [(loop.name, loop.singleton) for loop in MODULE.loops] == [
        ("product_crawl", True),
        ("product_view", True),
        ("product_three_view", True),
    ]


async def test_import_creates_pending_records_and_reports_failures(client, admin):
    response = await client.post(f"{BASE}/import", json={"skus": [" wtk9167；NOPE-1 ", "WTK9167"]}, headers=admin)

    assert response.status_code == 200
    body = response.json()
    assert len(body["created"]) == WTK9167_RECORDS
    assert {p["sku"] for p in body["created"]} == {"WTK9167"}
    assert {(p["crawl_status"], p["view_status"], p["gen_status"]) for p in body["created"]} == {
        ("pending", "pending", "pending"),
    }
    assert body["created"][0]["created_by"] == int(admin["X-User-Id"])
    assert body["skipped"] == 0
    assert [f["sku"] for f in body["failed"]] == ["NOPE-1"]


async def test_import_skips_existing_sku_asin(client, admin):
    first = (await client.post(f"{BASE}/import", json={"skus": ["WTK9167"]}, headers=admin)).json()
    removed = first["created"][0]
    assert (await client.delete(f"{BASE}/{removed['id']}", headers=admin)).status_code == 204

    second = (await client.post(f"{BASE}/import", json={"skus": ["wtk9167"]}, headers=admin)).json()

    assert second["skipped"] == WTK9167_RECORDS - 1
    assert [p["asin"] for p in second["created"]] == [removed["asin"]]


@pytest.mark.parametrize("skus", [[], [" ", ""], ["A"] * 51])
async def test_import_rejects_empty_or_oversized(client, admin, skus):
    response = await client.post(f"{BASE}/import", json={"skus": skus}, headers=admin)
    assert response.status_code == 422


async def test_import_requires_create_permission(client, session):
    plain = AppUser(username="import_plain", display_name="import_plain", is_active=True)
    session.add(plain)
    await session.flush()
    response = await client.post(f"{BASE}/import", json={"skus": ["WTK9167"]}, headers={"X-User-Id": str(plain.id)})
    assert response.status_code == 403


async def test_retry_resets_failed_stages(client, session, admin):
    product = ProductMaster(
        sku="R-1", crawl_status="failed", crawl_error="被拦截", view_status="pending", gen_status="pending",
    )
    session.add(product)
    await session.flush()

    def stages(response) -> tuple:
        body = response.json()
        return body["crawl_status"], body["view_status"], body["gen_status"]

    retried = await client.post(f"{BASE}/{product.id}/retry-import", headers=admin)
    assert retried.status_code == 200
    assert (retried.json()["crawl_status"], retried.json()["crawl_error"]) == ("pending", None)

    product.crawl_status, product.view_status, product.view_error = "done", "failed", "缺背面"
    product.gen_status = "pending"
    await session.flush()
    retried = await client.post(f"{BASE}/{product.id}/retry-import", headers=admin)
    assert stages(retried) == ("done", "pending", "pending")

    product.view_status, product.gen_status, product.gen_error = "done", "failed", "待人工确认"
    await session.flush()
    retried = await client.post(f"{BASE}/{product.id}/retry-import", headers=admin)
    assert stages(retried) == ("done", "done", "pending")
    assert retried.json()["gen_error"] is None

    assert (await client.post(f"{BASE}/{product.id}/retry-import", headers=admin)).status_code == 409


class FakeTool:
    """按输入返回预设结果；每次调用都发出停机信号，让循环处理完当前批次后退出。"""

    def __init__(self, stopping: asyncio.Event, respond) -> None:
        self._stopping = stopping
        self._respond = respond
        self.payloads: list[dict] = []

    async def execute(self, payload: dict, settings) -> ToolResult:
        self.payloads.append(payload)
        self._stopping.set()
        return self._respond(payload)


class FakeLLM:
    def __init__(self, **kwargs) -> None:
        pass

    async def aclose(self) -> None:
        pass


def _context(name: str) -> LoopContext:
    return LoopContext("tiktok_studio", name, asyncio.Event(), logging.getLogger(f"worker.tiktok_studio.{name}"))


@pytest.fixture
async def committed_products(db_ready):
    """worker 用 session_scope 自己提交事务，用例数据也要真实提交，结束后清理。"""
    created: list[int] = []

    async def add(**fields) -> int:
        async with session_scope() as session:
            product = ProductMaster(**fields)
            session.add(product)
            await session.flush()
            created.append(product.id)
            return product.id

    yield add
    async with session_scope() as session:
        await session.execute(delete(ProductMaster).where(ProductMaster.id.in_(created)))


async def _load(product_id: int) -> ProductMaster:
    async with session_scope() as session:
        return (await session.execute(select(ProductMaster).where(ProductMaster.id == product_id))).scalar_one()


def tos(key: str, url: str | None = None) -> dict:
    return {"key": key, "url": url, "type": "tos"}


class FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def get(self, provider: str):
        deleted = self.deleted

        class _Storage:
            def delete_file(self, key: str) -> None:
                deleted.append((provider, key))

        return _Storage()


@pytest.fixture
def storage(monkeypatch) -> FakeStorage:
    fake = FakeStorage()
    monkeypatch.setattr(service, "get_storage", fake.get)
    return fake


async def test_product_crawl_fills_details_and_records_failures(monkeypatch, committed_products, storage):
    ok_id = await committed_products(
        sku="C-1", asin="B0OK000001", crawl_status="pending", view_status="pending",
        main_image=tos("amazon/B0OK000001/01_MAIN.jpg"), sub_images=[tos("amazon/B0OK000001/old.jpg")],
        import_trace={"crawl": {"input": {}, "output": {}, "error_code": None, "error_message": "上次失败"}},
    )
    bad_id = await committed_products(
        sku="C-2", asin="B0BAD00001", crawl_status="running", view_status="pending",
        import_trace={"view": {"input": {}, "output": {}, "error_code": None, "error_message": "上次"}},
    )
    ctx = _context("product_crawl")
    main = tos("amazon/B0OK000001/01_MAIN.jpg", "https://cdn/main.jpg")
    gallery = [tos("amazon/B0OK000001/02_PT01.jpg", "https://cdn/1.jpg"), tos("amazon/B0OK000001/03_PT02.jpg")]

    def respond(payload: dict) -> ToolResult:
        if payload["asin"] == "B0BAD00001":
            return ToolResult(False, {}, "amazon_blocked", "商品页被 Amazon 拦截")
        return ToolResult(True, {
            "title": "Tank",
            "bullet_points": ["透气", "修身"],
            "description": "纯棉背心",
            "main_image": {**main, "source_url": "https://m.media-amazon.com/main.jpg", "content_type": "image/jpeg"},
            "gallery_images": gallery,
        })

    crawler = FakeTool(ctx.stopping, respond)
    monkeypatch.setattr(worker, "get_storage", lambda: None)
    monkeypatch.setattr(worker.tools, "build", lambda name, deps: crawler)

    await asyncio.wait_for(worker.product_crawl(ctx), 5)

    ok = await _load(ok_id)
    assert (ok.crawl_status, ok.crawl_error, ok.view_status) == ("done", None, "pending")
    assert (ok.description, ok.selling_points) == ("纯棉背心", "透气\n修身")
    assert (ok.main_image, ok.sub_images) == (main, gallery)
    assert storage.deleted == [("tos", "amazon/B0OK000001/old.jpg")]    # 重新抓取后不再引用的旧图
    assert ok.import_trace == {}    # 成功后清掉该阶段上次失败的现场
    bad = await _load(bad_id)
    assert (bad.crawl_status, bad.crawl_error) == ("failed", "商品页被 Amazon 拦截")
    assert bad.import_trace["crawl"] == {
        "input": {"asin": "B0BAD00001"}, "output": {},
        "error_code": "amazon_blocked", "error_message": "商品页被 Amazon 拦截",
    }
    assert bad.import_trace["view"]["error_message"] == "上次"


async def test_product_view_writes_reference_images(monkeypatch, committed_products):
    main, sub1, sub2 = (tos(f"k/{n}.jpg", f"https://cdn/{n}.jpg") for n in ("main", "1", "2"))
    ok_id = await committed_products(
        sku="V-1", crawl_status="done", view_status="pending", selling_points="透气\n修身", description="背心",
        main_image=main, sub_images=[sub1, sub2, tos("k/private.jpg")],
    )
    few_id = await committed_products(
        sku="V-2", crawl_status="done", view_status="pending", main_image=tos("k/only.jpg", "https://cdn/only.jpg"),
    )
    waiting_id = await committed_products(sku="V-3", crawl_status="pending", view_status="pending")
    ctx = _context("product_view")

    def respond(payload: dict) -> ToolResult:
        return ToolResult(True, {
            "front_url": "https://cdn/main.jpg", "back_url": "https://cdn/2.jpg", "side_url": None, "side_kind": "none",
        })

    selector = FakeTool(ctx.stopping, respond)
    monkeypatch.setattr(worker, "AsyncLLMClient", FakeLLM)
    monkeypatch.setattr(worker.tools, "build", lambda name, deps: selector)

    await asyncio.wait_for(worker.product_view(ctx), 5)

    assert selector.payloads == [{
        "images": ["https://cdn/main.jpg", "https://cdn/1.jpg", "https://cdn/2.jpg"],
        "bullet_points": ["透气", "修身"],
        "description": "背心",
    }]
    ok = await _load(ok_id)
    assert (ok.view_status, ok.three_view_reference_images) == ("done", [main, sub2])
    assert ok.three_view_side_kind == "none"
    few = await _load(few_id)
    assert few.view_status == "failed"
    assert "只有 1 张" in few.view_error
    assert few.import_trace["view"]["input"]["images"] == ["https://cdn/only.jpg"]
    assert (await _load(waiting_id)).view_status == "pending"


async def test_product_three_view_writes_generated_image(monkeypatch, committed_products, storage):
    done = {"crawl_status": "done", "view_status": "done", "gen_status": "pending"}

    def refs(*names: str) -> list[dict]:
        return [tos(f"k/{name}.jpg", f"https://cdn/{name}.jpg") for name in names]

    side_id = await committed_products(
        sku="G-1", asin="B0GEN00001", color="黑", selling_points="露肩\n长袖", description="上衣", **done,
        three_view_reference_images=refs("f", "s", "b"), three_view_side_kind="front_three_quarter",
        three_view_images=[tos("three_view/B0GEN00001/legacy.png"), tos("amazon/B0GEN00001/THREE_VIEW.png")],
    )
    confirm_id = await committed_products(
        sku="G-2", asin="B0GEN00002", **done, three_view_reference_images=refs("f2", "b2"), three_view_side_kind="none",
    )
    broken_id = await committed_products(
        sku="G-3", asin="B0GEN00003", **done, three_view_reference_images=refs("f3"), three_view_side_kind="none",
    )
    waiting_id = await committed_products(sku="G-4", crawl_status="done", view_status="pending", gen_status="pending")
    ctx = _context("product_three_view")
    generated = tos("amazon/B0GEN00001/THREE_VIEW.png", "https://cdn/amazon/B0GEN00001/THREE_VIEW.png")

    def respond(payload: dict) -> ToolResult:
        if payload["asin"] == "B0GEN00002":
            return ToolResult(False, {}, "needs_confirmation", "商品形态无法可靠确认")
        return ToolResult(True, {"image": generated})

    generator = FakeTool(ctx.stopping, respond)
    monkeypatch.setattr(worker, "GEN_CONCURRENCY", 3)
    monkeypatch.setattr(worker, "AsyncLLMClient", FakeLLM)
    monkeypatch.setattr(worker, "get_storage", lambda: None)
    monkeypatch.setattr(worker.tools, "build", lambda name, deps: generator)

    await asyncio.wait_for(worker.product_three_view(ctx), 5)

    assert generator.payloads[0] == {
        "asin": "B0GEN00001", "product_code": "G-1", "color": "黑",
        "bullet_points": ["露肩", "长袖"], "description": "上衣",
        "front_url": "https://cdn/f.jpg", "back_url": "https://cdn/b.jpg",
        "side_url": "https://cdn/s.jpg", "side_kind": "front_three_quarter",
    }
    assert (generator.payloads[1]["back_url"], generator.payloads[1]["side_url"]) == ("https://cdn/b2.jpg", None)
    ok = await _load(side_id)
    assert (ok.gen_status, ok.gen_error, ok.three_view_images) == ("done", None, [generated])
    assert storage.deleted == [("tos", "three_view/B0GEN00001/legacy.png")]    # 覆盖写入的同名对象不删
    confirm = await _load(confirm_id)
    assert (confirm.gen_status, confirm.gen_error) == ("failed", "商品形态无法可靠确认")
    assert confirm.import_trace["gen"]["input"] == generator.payloads[1]
    assert confirm.import_trace["gen"]["error_code"] == "needs_confirmation"
    broken = await _load(broken_id)
    assert broken.gen_status == "failed" and "不符" in broken.gen_error
    assert (await _load(waiting_id)).gen_status == "pending"


async def test_unexpected_tool_exception_marks_failed(monkeypatch, committed_products):
    product_id = await committed_products(sku="E-1", asin="B0ERR00001", crawl_status="pending", view_status="pending")
    ctx = _context("product_crawl")

    def respond(payload: dict) -> ToolResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "get_storage", lambda: None)
    monkeypatch.setattr(worker.tools, "build", lambda name, deps: FakeTool(ctx.stopping, respond))

    await asyncio.wait_for(worker.product_crawl(ctx), 5)

    product = await _load(product_id)
    assert (product.crawl_status, product.crawl_error) == ("failed", "RuntimeError: boom")
    assert product.import_trace["crawl"]["error_code"] == "unexpected_error"
