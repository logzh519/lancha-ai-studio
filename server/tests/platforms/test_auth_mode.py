"""auth_mode 开关：默认不改变现有行为，开启后配置残缺必须启动即失败。"""

import pytest
from fastapi import Request
from pydantic import ValidationError

from platforms.auth import session as auth_session
from platforms.auth.principal import Principal, current_principal
from platforms.config import Settings
from platforms.gateway.app import create_app


def test_default_auth_mode_is_dev_header(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert Settings(_env_file=None).auth_mode == "dev_header"


def test_invalid_auth_mode_raises_validation_error():
    with pytest.raises(ValidationError):
        Settings(auth_mode="feishu_typo", _env_file=None)


def test_feishu_mode_requires_full_configuration():
    settings = Settings(auth_mode="feishu", feishu_app_id="cli_x", feishu_app_secret="", feishu_redirect_uri="")
    with pytest.raises(RuntimeError, match="FEISHU"):
        create_app(settings)


def test_feishu_mode_starts_with_full_configuration():
    settings = Settings(
        auth_mode="feishu",
        feishu_app_id="cli_x",
        feishu_app_secret="secret",
        feishu_redirect_uri="https://app.test/api/platform/auth/feishu/callback",
    )
    assert create_app(settings) is not None


async def test_auth_provider_is_scoped_to_each_app(monkeypatch):
    feishu_app = create_app(
        Settings(
            auth_mode="feishu",
            feishu_app_id="cli_x",
            feishu_app_secret="secret",
            feishu_redirect_uri="https://app.test/api/platform/auth/feishu/callback",
        )
    )
    dev_app = create_app(Settings(auth_mode="dev_header"))

    async def resolve(session, raw_token):
        assert raw_token == "feishu-token"
        return Principal(user_id=42)

    monkeypatch.setattr(auth_session, "resolve", resolve)

    def request(headers):
        return Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": headers,
                "client": ("test", 1),
                "server": ("test", 80),
            }
        )

    dev_provider = dev_app.dependency_overrides[current_principal]
    feishu_provider = feishu_app.dependency_overrides[current_principal]
    dev_principal = await dev_provider(request([(b"x-user-id", b"7")]), object())
    feishu_principal = await feishu_provider(
        request([(b"cookie", b"lancha_session=feishu-token")]), object()
    )

    assert dev_principal.user_id == 7
    assert feishu_principal.user_id == 42
