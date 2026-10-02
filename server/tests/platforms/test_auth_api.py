"""认证路由：登录链路的端到端行为，含 state 重放、nonce 绑定与失败跳转。"""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from platforms.auth.api import build_feishu_client
from platforms.auth.feishu.client import FeishuClient
from platforms.auth.models import AppUser, UserSession
from platforms.auth.oauth_state import NONCE_COOKIE
from platforms.auth.session import SESSION_COOKIE, issue
from platforms.config import Settings
from platforms.db import get_session
from platforms.gateway.app import create_app

pytestmark = pytest.mark.db

SETTINGS = Settings(
    auth_mode="feishu",
    feishu_app_id="cli_x",
    feishu_app_secret="secret",
    feishu_redirect_uri="https://app.test/api/auth/feishu/callback",
    frontend_base_url="https://app.test",
)


def _feishu_handler(request: httpx.Request) -> httpx.Response:
    if "token" in str(request.url):
        return httpx.Response(200, json={"code": 0, "access_token": "u-token"})
    return httpx.Response(
        200,
        json={
            "code": 0,
            "data": {
                "open_id": "ou_1",
                "union_id": "on_1",
                "enterprise_email": "zhang.san@lancha.com",
                "name": "张三",
                "avatar_url": "https://example.com/a.png",
            },
        },
    )


@pytest.fixture
async def client(session):
    app = create_app(SETTINGS)

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[build_feishu_client] = lambda: FeishuClient(
        app_id="cli_x", app_secret="secret", transport=httpx.MockTransport(_feishu_handler)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://app.test") as c:
        yield c


async def _start_login(client) -> str:
    """走一遍 login-url 拿原始 state，nonce cookie 顺势落进客户端的 cookie 罐。"""
    response = await client.post("/api/auth/feishu/login-url")
    return parse_qs(urlparse(response.json()["authorize_url"]).query)["state"][0]


async def test_config_reports_feishu_is_configured(client):
    response = await client.get("/api/auth/config")
    assert response.json() == {"feishu_configured": True}


async def test_login_url_contains_state_and_redirect(client):
    response = await client.post("/api/auth/feishu/login-url")
    url = response.json()["authorize_url"]
    assert url.startswith("https://accounts.feishu.cn/open-apis/authen/v1/authorize?")
    assert "state=" in url


async def test_login_url_binds_state_to_this_browser_with_a_nonce_cookie(client):
    response = await client.post("/api/auth/feishu/login-url")

    assert response.cookies.get(NONCE_COOKIE)
    assert "httponly" in response.headers["set-cookie"].lower()


async def test_callback_creates_session_and_redirects_home(client, session):
    raw_state = await _start_login(client)

    response = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://app.test/"
    assert response.cookies.get(SESSION_COOKIE)
    user = (await session.execute(select(AppUser))).scalars().one()
    assert user.username == "zhang.san@lancha.com"


async def test_callback_rejects_replayed_state(client, session):
    raw_state = await _start_login(client)
    await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    replayed = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert replayed.status_code == 302
    assert replayed.headers["location"].startswith("https://app.test/login?error=")


async def test_callback_rejects_state_without_matching_nonce_cookie(client, session):
    """攻击者授权好的 state 被诱导到受害者浏览器上打开——那里没有对应的 nonce。"""
    raw_state = await _start_login(client)
    client.cookies.clear()

    response = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://app.test/login?error=")
    assert response.cookies.get(SESSION_COOKIE) is None
    assert (await session.execute(select(UserSession))).scalars().all() == []


async def test_callback_rejects_wrong_nonce_cookie(client, session):
    raw_state = await _start_login(client)
    client.cookies.set(NONCE_COOKIE, "someone-elses-nonce")

    response = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert response.headers["location"].startswith("https://app.test/login?error=")
    assert (await session.execute(select(UserSession))).scalars().all() == []


async def test_callback_clears_the_nonce_cookie(client):
    raw_state = await _start_login(client)

    await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert not client.cookies.get(NONCE_COOKIE)


async def test_callback_with_authorization_error_redirects_to_login(client):
    response = await client.get(
        "/api/auth/feishu/callback",
        params={"error": "access_denied", "state": "whatever"},
        follow_redirects=False,
    )
    assert response.headers["location"].startswith("https://app.test/login?error=")


async def test_callback_refuses_deactivated_user(client, session):
    session.add(AppUser(username="zhang.san@lancha.com", is_superuser=False, is_active=False))
    await session.flush()
    raw_state = await _start_login(client)

    response = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    assert response.headers["location"].startswith("https://app.test/login?error=")
    assert response.cookies.get(SESSION_COOKIE) is None
    assert (await session.execute(select(UserSession))).scalars().all() == []


async def test_me_requires_login(client):
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_me_returns_profile_after_login(client, session):
    raw_state = await _start_login(client)
    await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )

    body = (await client.get("/api/auth/me")).json()

    assert body["username"] == "zhang.san@lancha.com"
    assert body["display_name"] == "张三"
    assert body["avatar_url"] == "https://example.com/a.png"
    assert body["superuser"] is False


async def test_logout_clears_session(client, session):
    raw_state = await _start_login(client)
    login = await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )
    old_cookie = login.cookies.get(SESSION_COOKIE)

    assert (await client.post("/api/auth/logout")).status_code == 204
    # 响应会删 cookie，客户端 cookie 罐不可靠；手动塞回旧 token 证明服务端已撤销会话。
    client.cookies.set(SESSION_COOKIE, old_cookie)
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await session.execute(select(UserSession))).scalars().all() == []


async def test_logout_only_revokes_current_device_session(client, session):
    raw_state = await _start_login(client)
    await client.get(
        "/api/auth/feishu/callback",
        params={"code": "the-code", "state": raw_state},
        follow_redirects=False,
    )
    user = (await session.execute(select(AppUser))).scalars().one()
    other_device_token = await issue(session, user.id, timedelta(days=7))

    assert (await client.post("/api/auth/logout")).status_code == 204
    client.cookies.set(SESSION_COOKIE, other_device_token)
    assert (await client.get("/api/auth/me")).status_code == 200
    assert len((await session.execute(select(UserSession))).scalars().all()) == 1
