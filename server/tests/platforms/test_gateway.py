"""网关装配：路由挂载前缀、请求上下文、统一错误响应。"""

import pytest
from httpx import ASGITransport, AsyncClient

from platforms.gateway.app import create_app
from platforms.gateway.middleware import REQUEST_ID_HEADER


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
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
    paths = set(create_app().openapi()["paths"])
    assert "/api/example/items" in paths
    assert "/api/platform/modules" in paths
