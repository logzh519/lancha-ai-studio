"""飞书客户端：端点回退、错误识别与资料归一。全部走 mock transport，不打真实网络。"""

import json

import httpx
import pytest

from platforms.auth.feishu.client import TOKEN_URLS, FeishuClient, FeishuError

USER_INFO_BODY = {
    "code": 0,
    "msg": "ok",
    "data": {
        "open_id": "ou_1",
        "union_id": "on_1",
        "enterprise_email": "Zhang.San@Lancha.com",
        "name": "张三",
        "en_name": "Zhang San",
        "avatar_url": "https://example.com/a.png",
    },
}


def _client(handler) -> FeishuClient:
    return FeishuClient(app_id="cli_x", app_secret="secret", transport=httpx.MockTransport(handler))


def test_client_repr_does_not_expose_app_secret():
    client = _client(lambda request: httpx.Response(200))
    text = repr(client)
    assert "secret" not in text
    assert "app_secret" not in text


def test_authorize_url_carries_client_id_state_and_scope():
    url = _client(lambda request: httpx.Response(200)).authorize_url(
        "https://app.test/api/platform/auth/feishu/callback", "st4te", "auth:user.id:read"
    )

    assert url.startswith("https://accounts.feishu.cn/open-apis/authen/v1/authorize?")
    assert "client_id=cli_x" in url
    assert "state=st4te" in url
    assert "scope=auth%3Auser.id%3Aread" in url
    assert "response_type=code" in url


def test_authorize_url_encodes_scope_with_percent20_and_escapes_redirect_query():
    scopes = "auth:user.id:read contact:user.employee:readonly"
    redirect = "https://app.test/cb?tenant=1&from=web"
    url = _client(lambda request: httpx.Response(200)).authorize_url(redirect, "st", scopes)

    assert "scope=auth%3Auser.id%3Aread%20contact%3Auser.employee%3Areadonly" in url
    assert "scope=" in url and "+" not in url.split("scope=")[1].split("&")[0]
    assert "redirect_uri=https%3A%2F%2Fapp.test%2Fcb%3Ftenant%3D1%26from%3Dweb" in url


async def test_exchange_falls_back_to_legacy_endpoint():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "accounts.feishu.cn" in str(request.url):
            return httpx.Response(500, json={"code": 99, "msg": "boom"})
        return httpx.Response(200, json={"code": 0, "access_token": "u-token"})

    token = await _client(handler).exchange("the-code", "https://app.test/cb")

    assert token == "u-token"
    assert len(seen) == 2
    assert "open.feishu.cn" in seen[1]


async def test_exchange_raises_when_both_endpoints_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20001, "msg": "invalid code"})

    with pytest.raises(FeishuError) as exc_info:
        await _client(handler).exchange("bad-code", "https://app.test/cb")

    msg = str(exc_info.value)
    assert TOKEN_URLS[0] in msg
    assert TOKEN_URLS[1] in msg


async def test_user_info_is_normalised_into_external_profile():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer u-token"
        return httpx.Response(200, json=USER_INFO_BODY)

    profile = await _client(handler).user_info("u-token")

    assert profile.provider == "feishu"
    assert profile.external_id == "ou_1"
    assert profile.union_id == "on_1"
    assert profile.email == "Zhang.San@Lancha.com"
    assert profile.display_name == "张三"
    assert profile.avatar_url == "https://example.com/a.png"


async def test_user_info_raises_on_business_error_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"code": 99991663, "msg": "token expired"}))

    with pytest.raises(FeishuError):
        await _client(handler).user_info("stale")


async def test_user_info_without_open_id_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "data": {"name": "张三"}})

    with pytest.raises(FeishuError):
        await _client(handler).user_info("u-token")
