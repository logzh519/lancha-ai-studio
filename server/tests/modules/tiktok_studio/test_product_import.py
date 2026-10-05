"""按货号批量导入：同步入库与去重、失败阶段重试，以及 worker 的抓取、三视图两个后台阶段。"""

import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from modules.tiktok_studio import worker
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
    ]


async def test_import_creates_pending_records_and_reports_failures(client, admin):
    response = await client.post(f"{BASE}/import", json={"skus": [" wtk9167；NOPE-1 ", "WTK9167"]}, headers=admin)

    assert response.status_code == 200
    body = response.json()
    assert len(body["created"]) == WTK9167_RECORDS
    assert {p["sku"] for p in body["created"]} == {"WTK9167"}
    assert {(p["crawl_status"], p["view_status"]) for p in body["created"]} == {("pending", "pending")}
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
    product = ProductMaster(sku="R-1", crawl_status="failed", crawl_error="被拦截", view_status="pending")
    session.add(product)
    await session.flush()

    retried = await client.post(f"{BASE}/{product.id}/retry-import", headers=admin)
    assert retried.status_code == 200
    assert (retried.json()["crawl_status"], retried.json()["crawl_error"]) == ("pending", None)

    product.crawl_status, product.view_status, product.view_error = "done", "failed", "缺背面"
    await session.flush()
    retried = await client.post(f"{BASE}/{product.id}/retry-import", headers=admin)
    assert (retried.json()["crawl_status"], retried.json()["view_status"]) == ("done", "pending")

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


async def test_product_crawl_fills_details_and_records_failures(monkeypatch, committed_products):
    ok_id = await committed_products(sku="C-1", asin="B0OK000001", crawl_status="pending", view_status="pending")
    bad_id = await committed_products(sku="C-2", asin="B0BAD00001", crawl_status="running", view_status="pending")
    ctx = _context("product_crawl")

    def respond(payload: dict) -> ToolResult:
        if payload["asin"] == "B0BAD00001":
            return ToolResult(False, {}, "amazon_blocked", "商品页被 Amazon 拦截")
        return ToolResult(True, {
            "title": "Tank",
            "bullet_points": ["透气", "修身"],
            "description": "纯棉背心",
            "main_image": {"url": "https://cdn/main.jpg"},
            "gallery_images": [{"url": "https://cdn/1.jpg"}, {"url": None}, {"url": "https://cdn/2.jpg"}],
        })

    crawler = FakeTool(ctx.stopping, respond)
    monkeypatch.setattr(worker, "get_storage", lambda: None)
    monkeypatch.setattr(worker.tools, "build", lambda name, deps: crawler)

    await asyncio.wait_for(worker.product_crawl(ctx), 5)

    ok = await _load(ok_id)
    assert (ok.crawl_status, ok.crawl_error, ok.view_status) == ("done", None, "pending")
    assert (ok.description, ok.selling_points) == ("纯棉背心", "透气\n修身")
    assert ok.main_image_url == "https://cdn/main.jpg"
    assert ok.sub_images == ["https://cdn/1.jpg", "https://cdn/2.jpg"]
    bad = await _load(bad_id)
    assert (bad.crawl_status, bad.crawl_error) == ("failed", "商品页被 Amazon 拦截")


async def test_product_view_writes_reference_images(monkeypatch, committed_products):
    ok_id = await committed_products(
        sku="V-1", crawl_status="done", view_status="pending", selling_points="透气\n修身", description="背心",
        main_image_url="https://cdn/main.jpg", sub_images=["https://cdn/1.jpg", "https://cdn/2.jpg"],
    )
    few_id = await committed_products(
        sku="V-2", crawl_status="done", view_status="pending", main_image_url="https://cdn/only.jpg",
    )
    waiting_id = await committed_products(sku="V-3", crawl_status="pending", view_status="pending")
    ctx = _context("product_view")

    def respond(payload: dict) -> ToolResult:
        return ToolResult(True, {"front_url": "https://cdn/main.jpg", "back_url": "https://cdn/2.jpg", "side_url": None})

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
    assert (ok.view_status, ok.three_view_reference_images) == ("done", ["https://cdn/main.jpg", "https://cdn/2.jpg"])
    few = await _load(few_id)
    assert few.view_status == "failed"
    assert "只有 1 张" in few.view_error
    assert (await _load(waiting_id)).view_status == "pending"


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
