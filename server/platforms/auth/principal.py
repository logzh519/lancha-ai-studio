"""当前请求的主体。

AUTH_MODE=dev_header 时从 X-User-Id 请求头取用户，仅供本地开发和自测使用；
AUTH_MODE=feishu 时由 create_app() 为该 app 装上基于会话 cookie 的实现。
换别的认证方式（JWT / 网关透传等）也走同一个钩子，平台和模块代码不用改，
因为大家都只依赖 current_principal。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.db import get_session


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    is_superuser: bool = False

    @property
    def is_anonymous(self) -> bool:
        return self.user_id is None


ANONYMOUS = Principal(user_id=None)

PrincipalProvider = Callable[[Request, AsyncSession], Awaitable[Principal]]


async def _dev_header_provider(request: Request, session: AsyncSession) -> Principal:
    raw = request.headers.get("X-User-Id")
    if raw is None or not raw.isdigit():
        return ANONYMOUS
    return Principal(user_id=int(raw))


async def session_provider(request: Request, session: AsyncSession) -> Principal:
    """生产实现：从 HttpOnly cookie 读会话。由 create_app() 按 app 配置装载。

    session 由调用方注入而不是自己建连接——自己建会绕开 FastAPI 的依赖体系，
    测试里对 get_session 的覆盖就对它失效了。
    """
    from platforms.auth.session import SESSION_COOKIE, resolve

    return await resolve(session, request.cookies.get(SESSION_COOKIE, "")) or ANONYMOUS


async def _resolve_principal(
    provider: PrincipalProvider, request: Request, session: AsyncSession
) -> Principal:
    principal = await provider(request, session)
    request.state.principal = principal
    return principal


def principal_dependency(provider: PrincipalProvider | None = None):
    """Create an app-scoped dependency using the selected authentication provider."""
    selected_provider = provider or _dev_header_provider

    async def dependency(
        request: Request, session: Annotated[AsyncSession, Depends(get_session)]
    ) -> Principal:
        return await _resolve_principal(selected_provider, request, session)

    return dependency


async def current_principal(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Principal:
    """默认开发认证依赖；create_app() 会按 app 配置替换它。"""
    return await _resolve_principal(_dev_header_provider, request, session)
