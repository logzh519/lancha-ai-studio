"""网关装配：路由挂载前缀、请求上下文、统一错误响应。"""

import pytest
from httpx import ASGITransport, AsyncClient

from platforms.config import Settings
from platforms.contract import ModuleSpec
from platforms.gateway import app as gateway_app
from platforms.gateway.app import create_app
from platforms.gateway.middleware import REQUEST_ID_HEADER


@pytest.fixture
async def client():
    app = create_app(Settings(auth_mode="dev_header"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health_lists_loaded_modules(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "modules": ["example"]}


async def test_request_id_is_echoed_back(client):
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "abc123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc123"


async def test_unknown_path_uses_unified_error_body(client):
    response = await client.get("/api/nope")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 404
    assert body["request_id"]


async def test_module_router_is_mounted_under_module_prefix():
    paths = set(create_app(Settings(auth_mode="dev_header")).openapi()["paths"])
    assert "/api/example/items" in paths
    assert "/api/platform/modules" in paths


async def test_shutdown_continues_after_hook_failure(monkeypatch):
    calls = []

    async def failing_shutdown():
        calls.append("failing")
        raise RuntimeError("shutdown failed")

    async def later_shutdown():
        calls.append("later")

    async def dispose():
        calls.append("dispose")

    monkeypatch.setattr(gateway_app, "dispose_engine", dispose)
    app = create_app(Settings(auth_mode="dev_header"))
    app.router.lifespan_context = gateway_app._lifespan(
        [
            ModuleSpec(name="first", title="First", on_shutdown=failing_shutdown),
            ModuleSpec(name="second", title="Second", on_shutdown=later_shutdown),
        ]
    )

    async with app.router.lifespan_context(app):
        pass

    assert calls == ["later", "failing", "dispose"]
