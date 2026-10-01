"""当前请求的主体。

AUTH_MODE=dev_header 时从 X-User-Id 请求头取用户，仅供本地开发和自测使用；
AUTH_MODE=feishu 时由 create_app() 调 set_principal_provider() 装上基于会话 cookie 的实现。
换别的认证方式（JWT / 网关透传等）也走同一个钩子，平台和模块代码不用改，
因为大家都只依赖 current_principal。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

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
    """生产实现：从 HttpOnly cookie 读会话。由 create_app() 在 auth_mode=feishu 时装上。

    session 由调用方注入而不是自己建连接——自己建会绕开 FastAPI 的依赖体系，
    测试里对 get_session 的覆盖就对它失效了。
    """
    from platforms.auth.session import SESSION_COOKIE, resolve

    return await resolve(session, request.cookies.get(SESSION_COOKIE, "")) or ANONYMOUS


_provider: PrincipalProvider = _dev_header_provider


def set_principal_provider(provider: PrincipalProvider) -> None:
    global _provider
    _provider = provider


def reset_principal_provider() -> None:
    """还原默认实现。create_app() 会改全局状态，测试用例之间必须还原。"""
    set_principal_provider(_dev_header_provider)


async def current_principal(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Principal:
    """FastAPI 依赖：解析当前主体并挂到 request.state，供日志和后续依赖复用。"""
    principal = await _provider(request, session)
    request.state.principal = principal
    return principal
