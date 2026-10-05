"""统一 LLM 客户端门面：client.chat.completions.create(...) 与 OpenAI 同构。

LLMClient 为同步版；AsyncLLMClient 为异步版（chat 后端主链路使用）。
"""
from __future__ import annotations

from typing import Any

from platforms.config import get_settings
from platforms.llm.errors import LLMError
from platforms.llm.providers.anthropic_provider import (
    AnthropicProvider,
    AsyncAnthropicProvider,
)
from platforms.llm.providers.openai_provider import AsyncOpenAIProvider, OpenAIProvider


def _resolve_config(
        provider: str | None,   # 模型提供厂商: ali, openai, anthropic, glm，qwen, doubao, deepseek
        protocol: str | None    # 协议: openai兼容, anthropic兼容
    ) -> dict[str, Any]:

    settings = get_settings()
    if provider == "lch":
        if protocol == "anthropic":
            raise LLMError("朗驰（lch）仅支持 openai 协议")
        base_url = settings.lch_openai_base_url
        api_key = settings.lch_api_key
        model = settings.lch_llm_model
        image_model = settings.lch_image_model
    elif provider == "lch_tk":
        if protocol == "anthropic":
            raise LLMError("朗驰 TK（lch_tk）仅支持 openai 协议")
        base_url = settings.lch_tk_openai_base_url
        api_key = settings.lch_tk_api_key
        model = settings.lch_tk_llm_model
        image_model = None
    elif provider in (None, "ali"):
        base_url = settings.ali_anthropic_base_url if protocol == "anthropic" else settings.ali_openai_base_url
        api_key = settings.ali_api_key
        model = settings.ali_test_llm_model
        image_model = None
    else:
        raise LLMError(f"未知 provider {provider!r}，支持 ali / lch / lch_tk")

    config: dict[str, Any] = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "image_model": image_model,
        "protocol": protocol or "openai"  # 默认采用openai的协议
    }

    # 该代码是如果外部有传参则替换（目前被重构了没用）
    if base_url:
        config["base_url"] = base_url
    if api_key:
        config["api_key"] = api_key
    if model:
        config["model"] = model
    return config


class _Completions:
    def __init__(self, provider, default_model: str | None):
        self._provider = provider
        self._default_model = default_model

    def create(self, **params):
        if params.get("model") is None:
            params["model"] = self._default_model
        if not params.get("model"):
            raise LLMError("未指定 model：请传入 model 参数或配置 ALI_LLM_QWEN3_7_MAX")
        return self._provider.create(**params)


class _AsyncCompletions:
    def __init__(self, provider, default_model: str | None):
        self._provider = provider
        self._default_model = default_model

    async def create(self, **params):
        if params.get("model") is None:
            params["model"] = self._default_model
        if not params.get("model"):
            raise LLMError("未指定 model：请传入 model 参数或配置 ALI_LLM_QWEN3_7_MAX")
        return await self._provider.create(**params)


class _Chat:
    def __init__(self, completions):
        self.completions = completions


def _prepare_image_params(provider, default_model: str | None, params: dict) -> dict:
    if not hasattr(provider, "generate_image"):
        raise LLMError("当前协议不支持图片生成，请使用 openai 协议")
    if params.get("model") is None:
        params["model"] = default_model
    if not params.get("model"):
        raise LLMError("未指定 model：请传入 model 参数或配置图片模型（如 LCH_IMAGE_MODEL）")
    return params


class _Images:
    def __init__(self, provider, default_model: str | None):
        self._provider = provider
        self._default_model = default_model

    def generate(self, **params):
        params = _prepare_image_params(self._provider, self._default_model, params)
        return self._provider.generate_image(**params)

    def edit(self, **params):
        """参考图生图：image 可传单张或多张（文件路径 / 文件对象 / bytes 列表）。"""
        params = _prepare_image_params(self._provider, self._default_model, params)
        return self._provider.edit_image(**params)

    def edit_with_urls(self, *, image_urls: list[str], **params):
        """URL 参考图生图：image_urls 为参考图 URL 列表，其余参数同 edit（prompt / size / quality 等）。"""
        params = _prepare_image_params(self._provider, self._default_model, params)
        return self._provider.edit_image_with_urls(image_urls=image_urls, **params)


class _AsyncImages:
    def __init__(self, provider, default_model: str | None):
        self._provider = provider
        self._default_model = default_model

    async def generate(self, **params):
        params = _prepare_image_params(self._provider, self._default_model, params)
        return await self._provider.generate_image(**params)

    async def edit(self, **params):
        """参考图生图：image 可传单张或多张（文件路径 / 文件对象 / bytes 列表）。"""
        params = _prepare_image_params(self._provider, self._default_model, params)
        return await self._provider.edit_image(**params)

    async def edit_with_urls(self, *, image_urls: list[str], **params):
        """URL 参考图生图：image_urls 为参考图 URL 列表，其余参数同 edit（prompt / size / quality 等）。"""
        params = _prepare_image_params(self._provider, self._default_model, params)
        return await self._provider.edit_image_with_urls(image_urls=image_urls, **params)


class LLMClient:
    def __init__(self, protocol: str | None = None, provider: str | None = None):

        config = _resolve_config(provider, protocol)
        if config["protocol"] == "anthropic":
            self._provider = AnthropicProvider(config)
        elif config["protocol"] == "openai":
            self._provider = OpenAIProvider(config)
        else:
            raise LLMError(f"未知协议 {config['protocol']!r}，"
                           "支持 openai / anthropic")

        self.config = config
        self.chat = _Chat(_Completions(self._provider, config["model"]))
        self.images = _Images(self._provider, config["image_model"])


class AsyncLLMClient:
    def __init__(self, protocol: str | None = None, provider: str | None = None):
        config = _resolve_config(provider, protocol)

        if config["protocol"] == "anthropic":
            self._provider = AsyncAnthropicProvider(config)
        elif config["protocol"] == "openai":
            self._provider = AsyncOpenAIProvider(config)
        else:
            raise LLMError(f"未知协议 {config['protocol']!r}，"
                           "支持 openai / anthropic")

        self.config = config
        self.chat = _Chat(_AsyncCompletions(self._provider, config["model"]))
        self.images = _AsyncImages(self._provider, config["image_model"])

    async def aclose(self) -> None:
        """关闭底层 SDK 客户端的 httpx 连接池；应用 shutdown 时调用。"""
        await self._provider.client.close()
