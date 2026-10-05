"""阿里百炼兼容端点的 LLM 客户端连通性测试。

会向配置的模型发起真实请求，未配置 ALI_API_KEY 时跳过。
"""

import pytest

from platforms.config import get_settings
from platforms.llm import AsyncLLMClient, LLMClient

MESSAGES = [
    {"role": "system", "content": "你是天气查看助手。"},
    {"role": "user", "content": "今天厦门市天气怎么样？"},
]


@pytest.fixture(scope="module", autouse=True)
def require_ali_api_key():
    if not get_settings().ali_api_key:
        pytest.skip("未配置 ALI_API_KEY，跳过阿里 LLM 连通性测试")


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
def test_llm_client_completes_normal_chat(protocol: str):
    client = LLMClient(protocol=protocol)
    try:
        response = client.chat.completions.create(messages=MESSAGES)
    finally:
        client._provider.client.close()

    assert response.choices[0].message.content


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
async def test_async_llm_client_completes_normal_chat(protocol: str):
    client = AsyncLLMClient(protocol=protocol)
    try:
        response = await client.chat.completions.create(messages=MESSAGES)
    finally:
        await client.aclose()

    assert response.choices[0].message.content
