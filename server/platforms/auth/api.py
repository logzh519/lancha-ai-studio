"""认证路由，挂在 /api/auth 下。

回调是浏览器直接访问的地址，所以成功与失败都用 302 跳回前端，不返回 JSON——
用户看到的应该是登录页上的一句中文，而不是一屏报文。
"""

import hmac
import logging
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth import identity, oauth_state
from platforms.auth.feishu.client import FeishuClient, FeishuError
from platforms.auth.models import AppUser, UserIdentity
from platforms.auth.oauth_state import NONCE_COOKIE
from platforms.auth.principal import Principal, current_principal
from platforms.auth.session import SESSION_COOKIE, hash_token, issue, revoke
from platforms.config import Settings, get_settings
from platforms.db import get_session

logger = logging.getLogger("platform.auth")

router = APIRouter()

STATE_TTL = timedelta(minutes=10)


def build_feishu_client(settings: Settings = Depends(get_settings)) -> FeishuClient:
    return FeishuClient(app_id=settings.feishu_app_id, app_secret=settings.feishu_app_secret)


@router.get("/config")
async def auth_config(settings: Settings = Depends(get_settings)):
    """前端据此决定登录页上要不要显示飞书按钮。"""
    return {"feishu_configured": bool(settings.feishu_app_id and settings.feishu_redirect_uri)}


@router.post("/feishu/login-url")
async def feishu_login_url(
    response: Response,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    feishu: FeishuClient = Depends(build_feishu_client),
):
    state, nonce = await oauth_state.create(session, STATE_TTL)
    # nonce 明文只留在发起登录的这个浏览器里，回调时用它证明「state 是我自己要来的」。
    response.set_cookie(
        NONCE_COOKIE,
        nonce,
        max_age=int(STATE_TTL.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {
        "authorize_url": feishu.authorize_url(settings.feishu_redirect_uri, state, settings.feishu_scope),
        "expires_in": int(STATE_TTL.total_seconds()),
    }


@router.get("/feishu/callback")
async def feishu_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    feishu: FeishuClient = Depends(build_feishu_client),
):
    def failed(message: str) -> RedirectResponse:
        return RedirectResponse(f"{settings.frontend_base_url}/login?error={quote(message)}", status_code=302)

    async def complete() -> RedirectResponse:
        nonce_hash = await oauth_state.consume(session, state)
        if nonce_hash is None:
            return failed("飞书登录状态无效或已过期，请重新登录。")
        # state 对任何浏览器都有效，所以还要求发起方 cookie 里的 nonce 对得上，
        # 否则攻击者可以把自己授权好的回调地址丢给受害者点开，受害者就登进了攻击者的账号。
        if not hmac.compare_digest(nonce_hash, hash_token(request.cookies.get(NONCE_COOKIE, ""))):
            return failed("飞书登录状态无效或已过期，请重新登录。")
        if error:
            return failed("用户取消或拒绝了飞书授权。")
        if not code:
            return failed("飞书回调缺少授权码。")

        try:
            token = await feishu.exchange(code, settings.feishu_redirect_uri)
            profile = await feishu.user_info(token)
        except FeishuError as exc:
            return failed(str(exc))

        user = await identity.upsert(session, profile)
        if not user.is_active:
            # 不拦的话会签发一个永远解析不出身份的 cookie，用户只会被静默弹回登录页，
            # 完全看不出自己是被停用了。
            return failed("账号已被停用，请联系管理员。")
        raw = await issue(session, user.id, timedelta(days=settings.session_ttl_days))

        response = RedirectResponse(f"{settings.frontend_base_url}/", status_code=302)
        response.set_cookie(
            SESSION_COOKIE,
            raw,
            max_age=settings.session_ttl_days * 24 * 3600,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
        return response

    response = await complete()
    # nonce 是一次性的：留着它下一次回调就能拿旧 cookie 配新 state，绑定也就白做了。
    response.delete_cookie(NONCE_COOKIE, path="/")
    return response


@router.get("/me")
async def me(
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    if principal.is_anonymous:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录。")
    stmt = (
        select(AppUser.id, AppUser.username, AppUser.display_name, AppUser.is_superuser, UserIdentity.avatar_url)
        .outerjoin(UserIdentity, UserIdentity.user_id == AppUser.id)
        .where(AppUser.id == principal.user_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录。")
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name,
        "avatar_url": row.avatar_url or "",
        "superuser": row.is_superuser,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    # 用户在一台设备上登出，不应把其它设备上的会话一并作废；原始 token 仍在 cookie 里。
    if not principal.is_anonymous:
        await revoke(session, request.cookies.get(SESSION_COOKIE, ""))
    response.delete_cookie(SESSION_COOKIE, path="/")
