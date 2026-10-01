"""auth_mode 开关：默认不改变现有行为，开启后配置残缺必须启动即失败。"""

import pytest
from pydantic import ValidationError

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
