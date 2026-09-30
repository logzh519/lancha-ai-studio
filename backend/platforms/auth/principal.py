"""当前请求的主体。

本框架不实现认证。默认实现从 X-User-Id 请求头取用户，仅供本地开发和自测使用，
生产环境必须在启动时调用 set_principal_provider() 换成真实实现（JWT / Session / 网关透传等）。
替换后平台和模块代码不用改，因为大家都只依赖 current_principal。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    is_superuser: bool = False

    @property
    def is_anonymous(self) -> bool:
        return self.user_id is None


ANONYMOUS = Principal(user_id=None)

PrincipalProvider = Callable[[Request], Awaitable[Principal]]


async def _dev_header_provider(request: Request) -> Principal:
    raw = request.headers.get("X-User-Id")
    if raw is None or not raw.isdigit():
        return ANONYMOUS
    return Principal(user_id=int(raw))


_provider: PrincipalProvider = _dev_header_provider


def set_principal_provider(provider: PrincipalProvider) -> None:
    global _provider
    _provider = provider


async def current_principal(request: Request) -> Principal:
    """FastAPI 依赖：解析当前主体并挂到 request.state，供日志和后续依赖复用。"""
    principal = await _provider(request)
    request.state.principal = principal
    return principal
