"""飞书 OAuth 客户端。

整个工程里只有这个文件知道飞书的存在，换成别的账号系统时只替换它。
换 token 先打新域名，失败再回退老端点：两套端点在不同租户上的可用性不一致。
"""

from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

import httpx

from platforms.auth.identity import ExternalProfile

AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
TOKEN_URLS = (
    "https://accounts.feishu.cn/oauth/v3/token",
    "https://open.feishu.cn/open-apis/authen/v2/oauth/token",
)
USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
TIMEOUT = httpx.Timeout(20.0)


class FeishuError(Exception):
    """飞书接口返回了不可用的结果，调用方据此给用户一句中文提示。"""


@dataclass(frozen=True)
class FeishuClient:
    app_id: str
    # 默认 repr 会打印全部字段，日志/断言失败时会把密钥带出去
    app_secret: str = field(repr=False)
    transport: httpx.AsyncBaseTransport | None = None

    def authorize_url(self, redirect_uri: str, state: str, scope: str) -> str:
        query = {
            "client_id": self.app_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        if scope:
            query["scope"] = scope
        # 飞书文档用 %20 分隔 scope，quote_plus 会把空格编成 +
        return f"{AUTHORIZE_URL}?{urlencode(query, quote_via=quote)}"

    async def exchange(self, code: str, redirect_uri: str) -> str:
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        errors: list[str] = []
        async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT) as client:
            for url in TOKEN_URLS:
                try:
                    response = await client.post(url, json=payload)
                    body = response.json()
                except Exception as exc:
                    errors.append(f"{url} 请求失败：{exc}")
                    continue
                token = body.get("access_token", "")
                if response.status_code < 300 and body.get("code", 0) == 0 and token:
                    return token
                errors.append(
                    f"{url} 返回 status={response.status_code} code={body.get('code')} msg={body.get('msg')}"
                )
        detail = "; ".join(errors) if errors else "飞书未返回任何响应"
        raise FeishuError(f"换取飞书用户 token 失败：{detail}")

    async def user_info(self, access_token: str) -> ExternalProfile:
        async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT) as client:
            try:
                response = await client.get(USER_INFO_URL, headers={"authorization": f"Bearer {access_token}"})
                body = response.json()
            except Exception as exc:
                raise FeishuError(f"获取飞书用户信息失败：{exc}") from exc
        if response.status_code >= 300 or body.get("code", 0) != 0:
            raise FeishuError(
                f"获取飞书用户信息失败：status={response.status_code} code={body.get('code')} msg={body.get('msg')}"
            )

        data = body.get("data") or {}
        open_id = (data.get("open_id") or "").strip()
        if not open_id:
            raise FeishuError("飞书用户信息缺少 open_id，请检查应用的权限范围配置")
        return ExternalProfile(
            provider="feishu",
            external_id=open_id,
            union_id=(data.get("union_id") or "").strip(),
            email=(data.get("enterprise_email") or "").strip(),
            display_name=(data.get("name") or data.get("en_name") or "").strip(),
            avatar_url=(data.get("avatar_url") or data.get("avatar_thumb") or "").strip(),
        )
