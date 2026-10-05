"""three_view_gen：路由、提示词与 Tool 行为。LLM、图片下载、存储都用假实现，不打真实网络。"""

import base64
import io
import json
import struct
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from modules.tiktok_studio import tools
from modules.tiktok_studio.tools.three_view_gen_tool import (
    TEMPLATES,
    ThreeViewGenTool,
    prepare_template,
)
from platforms.llm import LLMError
from platforms.tools import ToolError

SETTINGS = tools.ToolSettings(timeout=5.0, trace_id="trace-1")
JPEG = b"\xff\xd8\xff\xe0fake"
RESULT_PNG = b"\x89PNG\r\n\x1a\nresult"
BASE_PAYLOAD = {
    "asin": "B0H8Z65GJT",
    "product_code": "WAT0025CSA0016",
    "color": "黑色",
    "title": "Women Off Shoulder Top",
    "front_url": "https://cdn.test/1.jpg",
    "back_url": "https://cdn.test/2.jpg",
    "side_url": "https://cdn.test/3.jpg",
    "side_kind": "front_three_quarter",
}
UPPER = json.dumps({"category": "upper", "confidence": 0.95, "reason": "仅售上衣"})
DETAILS = json.dumps({
    "critical_details": [
        {"fact": "cut the hem asymmetrically with a high-low shape", "confidence": 0.9},
        {"fact": "maybe a hidden pocket", "confidence": 0.5},
    ],
    "mannequin_limb_support": "not_required",
    "limb_reason": "none",
})


class FakeLLM:
    """chat_replies / image_replies 按顺序依次返回，最后一项一直重复；Exception 项会被抛出。"""

    def __init__(self, chat_replies: list, image_replies: list | None = None) -> None:
        self.chat_calls: list[dict] = []
        self.image_calls: list[dict] = []
        self._chat_replies = chat_replies
        self._image_replies = image_replies or [SimpleNamespace(data=[SimpleNamespace(
            b64_json=base64.b64encode(RESULT_PNG).decode(), url=None,
        )])]
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.images = SimpleNamespace(edit=self._edit)

    @staticmethod
    def _next(replies: list, calls: list):
        reply = replies[min(len(calls), len(replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def _create(self, **params):
        self.chat_calls.append(params)
        content = self._next(self._chat_replies, self.chat_calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    async def _edit(self, **params):
        self.image_calls.append(params)
        return self._next(self._image_replies, self.image_calls)


class FakeStorage:
    type = "tos"

    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}

    def upload(self, key, data, acl=None):
        self.uploaded[key] = data
        return SimpleNamespace(key=key, url=f"https://cdn.test/{key}")


def make_tool(llm: FakeLLM, storage: FakeStorage | None = None, status: int = 200) -> ThreeViewGenTool:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, content=JPEG))
    tool = ThreeViewGenTool(llm=llm, storage=storage or FakeStorage(), transport=transport)
    tool.retry_delays = (0, 0, 0)
    tool.image_retry_delays = (0,)
    return tool


def png_size(content: bytes) -> tuple[int, int]:
    assert content.startswith(b"\x89PNG")
    return struct.unpack(">II", content[16:24])


def test_prepare_template_pads_to_16_alignment_without_scaling():
    content, size = prepare_template(TEMPLATES["v3"], None)
    assert (size, png_size(content)) == ("1680x944", (1680, 944))
    with Image.open(io.BytesIO(content)) as padded, Image.open(TEMPLATES["v3"]) as source:
        left, top = (1680 - source.width) // 2, (944 - source.height) // 2
        assert padded.getpixel((0, 0)) == (255, 255, 255)
        assert padded.crop((left, top, left + source.width, top + source.height)).tobytes() == source.tobytes()


def test_prepare_template_keeps_aligned_template_as_is():
    assert prepare_template(TEMPLATES["v2"], None) == (TEMPLATES["v2"].read_bytes(), "2752x1536")


def test_prepare_template_honours_requested_size():
    content, size = prepare_template(TEMPLATES["v3"], "1920x1088")
    assert (size, png_size(content)) == ("1920x1088", (1920, 1088))


@pytest.mark.parametrize("size", ["1680x945", "1600x944"])
def test_prepare_template_rejects_unaligned_or_smaller_size(size):
    with pytest.raises(ToolError) as exc_info:
        prepare_template(TEMPLATES["v3"], size)
    assert exc_info.value.code == "invalid_size"


async def test_auto_upper_uses_v3_dummy_template_and_uploads_result():
    llm, storage = FakeLLM([UPPER, DETAILS]), FakeStorage()

    result = await make_tool(llm, storage).execute(BASE_PAYLOAD, SETTINGS)

    assert result.success, result.error_message
    output = result.output
    assert (output["generation_type"], output["workflow"], output["template"], output["size"]) == (
        "upper", "dummy_tryon", "v3", "1680x944",
    )
    assert output["classification"]["category"] == "upper"
    assert output["detail_lock"]["details"] == ["cut the hem asymmetrically with a high-low shape"]
    assert "- cut the hem asymmetrically with a high-low shape" in output["prompt"]
    assert "template + 正面 + 背面 + 斜侧面（侧面证据）" in output["prompt"]
    assert "V3 TEMPLATE SCOPE LOCK" in output["prompt"]
    key = "amazon/B0H8Z65GJT/THREE_VIEW.png"
    assert storage.uploaded == {key: RESULT_PNG}
    assert output["image"] == {"key": key, "url": f"https://cdn.test/{key}", "type": "tos"}

    classify, detail = llm.chat_calls
    assert classify["temperature"] == 0 and classify["timeout"] == SETTINGS.timeout
    assert len([p for p in classify["messages"][1]["content"] if p["type"] == "image_url"]) == 1
    assert len([p for p in detail["messages"][1]["content"] if p["type"] == "image_url"]) == 3

    (edit,) = llm.image_calls
    assert [name for name, _, _ in edit["image"]] == ["template.png", "front.jpeg", "back.jpeg", "side.jpeg"]
    assert png_size(edit["image"][0][1]) == (1680, 944)
    assert (edit["model"], edit["size"], edit["quality"]) == ("gpt-image-2", "1680x944", "medium")


async def test_explicit_set_uses_v2_template_without_classification():
    llm = FakeLLM([DETAILS])
    result = await make_tool(llm).execute({**BASE_PAYLOAD, "generation_type": "set"}, SETTINGS)

    assert result.success, result.error_message
    assert (result.output["template"], result.output["size"], result.output["classification"]) == (
        "v2", "2752x1536", None,
    )
    assert len(llm.chat_calls) == 1
    assert llm.image_calls[0]["image"][0][0] == "template.jpeg"


async def test_requested_size_applies_to_dummy_and_product_only():
    result = await make_tool(FakeLLM([DETAILS])).execute(
        {**BASE_PAYLOAD, "generation_type": "upper", "size": "1920x1088"}, SETTINGS,
    )
    assert result.output["size"] == "1920x1088"

    result = await make_tool(FakeLLM([])).execute(
        {**BASE_PAYLOAD, "generation_type": "bottom", "size": "1024x1024"}, SETTINGS,
    )
    assert result.output["size"] == "1024x1024"


async def test_invalid_template_size_fails_before_generation():
    llm = FakeLLM([DETAILS])
    result = await make_tool(llm).execute({**BASE_PAYLOAD, "generation_type": "upper", "size": "1000x1000"}, SETTINGS)
    assert (result.success, result.error_code) == (False, "invalid_size")
    assert llm.image_calls == []


async def test_bottom_uses_product_only_prompt_without_template():
    payload = {**BASE_PAYLOAD, "generation_type": "bottom", "side_url": None, "side_kind": "none"}
    llm = FakeLLM([])
    result = await make_tool(llm).execute(payload, SETTINGS)

    assert result.success, result.error_message
    output = result.output
    assert (output["workflow"], output["template"], output["size"], output["detail_lock"]) == (
        "product_only", None, "1536x1024", None,
    )
    assert "产品编码：WAT0025CSA0016" in output["prompt"] and "目标下装" in output["prompt"]
    assert "upload order is 正面 + 背面." in output["prompt"]
    assert llm.chat_calls == []
    assert [name for name, _, _ in llm.image_calls[0]["image"]] == ["front.jpeg", "back.jpeg"]


@pytest.mark.parametrize("reply", [
    json.dumps({"category": "upper", "confidence": 0.6, "reason": "不确定是否含裤子"}),
    json.dumps({"category": "jacket", "confidence": 0.99, "reason": "未知类型"}),
])
async def test_unreliable_classification_needs_confirmation(reply):
    llm = FakeLLM([reply])
    result = await make_tool(llm).execute(BASE_PAYLOAD, SETTINGS)

    assert (result.success, result.error_code) == (False, "needs_confirmation")
    assert llm.image_calls == []


async def test_classification_without_json_fails():
    result = await make_tool(FakeLLM(["no json"])).execute(BASE_PAYLOAD, SETTINGS)
    assert (result.success, result.error_code) == (False, "llm_invalid_output")


async def test_missing_detail_lock_falls_back_to_generic_prompt():
    no_details = json.dumps({"critical_details": [{"fact": "x", "confidence": 0.3}]})
    result = await make_tool(FakeLLM([UPPER, no_details])).execute(BASE_PAYLOAD, SETTINGS)

    assert result.success, result.error_message
    assert result.output["detail_lock"]["details"] == []
    assert result.output["detail_lock"]["error"]
    assert "PRODUCT-SPECIFIC CRITICAL DETAIL LOCK" not in result.output["prompt"]


async def test_image_generation_retries_transient_error_then_fails():
    llm = FakeLLM([UPPER, DETAILS], [LLMError("busy", 503, "api_error")])
    result = await make_tool(llm).execute(BASE_PAYLOAD, SETTINGS)

    assert (result.success, result.error_code) == (False, "image_generation_failed")
    assert len(llm.image_calls) == 2


async def test_image_generation_does_not_retry_bad_request():
    llm = FakeLLM([UPPER, DETAILS], [LLMError("bad size", 400, "invalid_request_error")])
    result = await make_tool(llm).execute(BASE_PAYLOAD, SETTINGS)

    assert result.error_code == "image_generation_failed"
    assert len(llm.image_calls) == 1


async def test_reference_download_failure():
    result = await make_tool(FakeLLM([UPPER]), status=403).execute(BASE_PAYLOAD, SETTINGS)
    assert (result.success, result.error_code) == (False, "image_download_failed")


async def test_side_url_and_side_kind_must_match():
    result = await make_tool(FakeLLM([])).execute({**BASE_PAYLOAD, "side_kind": "none"}, SETTINGS)
    assert result.error_code == "invalid_input"


def test_registry_requires_llm_and_storage():
    with pytest.raises(ValueError, match="storage"):
        tools.build("three_view_gen", tools.ToolDeps(session=None, llm=FakeLLM([])))
    deps = tools.ToolDeps(session=None, llm=FakeLLM([]), storage=FakeStorage())
    assert isinstance(tools.build("three_view_gen", deps), ThreeViewGenTool)
