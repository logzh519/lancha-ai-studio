"""OpenAI 协议：薄透传官方 SDK，仅做 base_url 归一与异常包装。"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Mapping

import httpx
import openai
from openai.types import ImagesResponse

from platforms.llm.errors import LLMError, wrap_error

logger = logging.getLogger("platform.llm")

# 参考图 URL 由本服务下载后以 data URL 发给上游：上游（海外）直连国内 TOS 会下载超时
_REF_DOWNLOAD_TIMEOUT = 60


def _normalize_base_url(base_url: str | None) -> str | None:
    """openai SDK 直接拼 /chat/completions，base_url 需带 /v1 前缀。"""
    if not base_url:
        return base_url
    trimmed = base_url.rstrip("/")
    return trimmed if trimmed.endswith("/v1") else trimmed + "/v1"


def _to_data_url(url: str, resp: httpx.Response) -> str:
    try:
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise LLMError(f"参考图下载失败 {url}: {e}", error_type="connection_error") from e
    mime = resp.headers.get("content-type", "image/png").split(";")[0]
    return f"data:{mime};base64,{base64.b64encode(resp.content).decode()}"


def _edit_body(data_urls: list[str], params: dict) -> dict:
    """/images/edits 的 JSON 请求体（SDK 的 images.edit 仅支持 multipart 文件上传）。"""
    return {**params, "images": [{"image_url": u} for u in data_urls]}


class OpenAIProvider:
    def __init__(self, config: Mapping[str, object]):
        self.client = openai.OpenAI(
            api_key=config.get("api_key"),
            base_url=_normalize_base_url(config.get("base_url")),
        )

    def create(self, **params):
        try:
            return self.client.chat.completions.create(**params)
        except openai.APIError as e:
            raise wrap_error(e) from e

    def generate_image(self, **params):
        try:
            return self.client.images.generate(**params)
        except openai.APIError as e:
            raise wrap_error(e) from e

    def edit_image(self, **params):
        try:
            return self.client.images.edit(**params)
        except openai.APIError as e:
            raise wrap_error(e) from e

    def edit_image_with_urls(self, *, image_urls: list[str], **params):
        try:
            with httpx.Client(timeout=_REF_DOWNLOAD_TIMEOUT, follow_redirects=True) as http:
                data_urls = [_to_data_url(u, http.get(u)) for u in image_urls]
        except httpx.HTTPError as e:
            raise LLMError(f"参考图下载失败: {e}", error_type="connection_error") from e
        try:
            return self.client.post("/images/edits", cast_to=ImagesResponse,
                                    body=_edit_body(data_urls, params))
        except openai.APIError as e:
            raise wrap_error(e) from e


class AsyncOpenAIProvider:
    """OpenAIProvider 的异步版：薄透传 AsyncOpenAI，仅做 base_url 归一与异常包装。"""

    def __init__(self, config: Mapping[str, object]):
        self.client = openai.AsyncOpenAI(
            api_key=config.get("api_key"),
            base_url=_normalize_base_url(config.get("base_url")))

    async def create(self, **params):
        try:
            return await self.client.chat.completions.create(**params)
        except openai.APIError as e:
            raise wrap_error(e) from e

    async def generate_image(self, **params):
        try:
            return await self.client.images.generate(**params)
        except openai.APIError as e:
            raise wrap_error(e) from e

    async def edit_image(self, **params):
        try:
            return await self.client.images.edit(**params)
        except openai.APIError as e:
            raise wrap_error(e) from e

    async def edit_image_with_urls(self, *, image_urls: list[str], **params):
        try:
            async with httpx.AsyncClient(timeout=_REF_DOWNLOAD_TIMEOUT,
                                         follow_redirects=True) as http:
                resps = await asyncio.gather(*(http.get(u) for u in image_urls))
        except httpx.HTTPError as e:
            raise LLMError(f"参考图下载失败: {e}", error_type="connection_error") from e
        data_urls = [_to_data_url(u, r) for u, r in zip(image_urls, resps)]
        body = _edit_body(data_urls, params)
        logger.debug("POST %simages/edits %s", self.client.base_url,
                     {**body, "images": [{"image_url": i["image_url"][:80] + "..."}
                                         for i in body["images"]]})
        try:
            return await self.client.post("/images/edits", cast_to=ImagesResponse, body=body)
        except openai.APIError as e:
            raise wrap_error(e) from e
