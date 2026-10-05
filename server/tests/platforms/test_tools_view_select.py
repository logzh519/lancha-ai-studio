"""view_select：视角挑选规则与 Tool 行为。LLM 与图片下载都用假实现，不打真实网络。"""

import json
from types import SimpleNamespace

import httpx
import pytest

from platforms.llm import LLMError
from platforms.tools import ToolDeps, ToolError, ToolSettings, platform_tools
from platforms.tools.view_select import (
    ViewSelectTool,
    parse_view_analysis,
    text_facts,
    validate_view_selection,
)

SETTINGS = ToolSettings(timeout=5.0, trace_id="trace-1")
JPEG = b"\xff\xd8\xff\xe0fake"


def candidate(index, view, confidence=0.9, side_evidence=0.0, same_color=True):
    return {"index": index, "view": view, "confidence": confidence, "same_product": True,
            "same_color": same_color, "side_evidence": side_evidence, "reason": "r"}


def model_text(candidates, selection):
    return "```json\n" + json.dumps({"candidates": candidates, "selection": selection}) + "\n```"


class FakeLLM:
    """reply 为列表时按顺序依次返回，最后一项一直重复；Exception 项会被抛出。"""

    def __init__(self, reply: str | Exception | list[str | Exception]) -> None:
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._replies = reply if isinstance(reply, list) else [reply]

    async def _create(self, **params):
        self.calls.append(params)
        reply = self._replies[min(len(self.calls), len(self._replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        message = SimpleNamespace(content=reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def image_urls(count: int) -> list[str]:
    return [f"https://cdn.test/{i}.jpg" for i in range(1, count + 1)]


def make_tool(llm: FakeLLM, status: int = 200) -> ViewSelectTool:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, content=JPEG, headers={"content-type": "application/octet-stream"})
    )
    tool = ViewSelectTool(llm=llm, transport=transport)
    tool.retry_delays = (0, 0, 0)
    return tool


def test_missing_back_selection_recovered_from_candidates():
    text = model_text(
        [candidate(1, "front"), candidate(2, "detail"), candidate(3, "back_three_quarter", 0.8)],
        {"front": 1, "back": None, "side": None, "confidence": 0.9},
    )
    analysis = parse_view_analysis(text, 3)
    assert (analysis["front"], analysis["back"]) == (1, 3)


def test_exact_view_preferred_over_oblique():
    text = model_text(
        [candidate(1, "front_three_quarter", 0.99), candidate(2, "front", 0.7), candidate(3, "back")],
        {"front": None, "back": 3},
    )
    assert parse_view_analysis(text, 3)["front"] == 2


def test_other_colorway_excluded():
    text = model_text(
        [candidate(1, "front"), candidate(2, "back", same_color=False), candidate(3, "back", 0.6)],
        {"front": 1, "back": 2},
    )
    assert parse_view_analysis(text, 3)["back"] == 3


def test_side_fallback_prefers_true_side_then_evidence():
    text = model_text(
        [candidate(1, "front"), candidate(2, "back"), candidate(3, "front_three_quarter", side_evidence=0.9),
         candidate(4, "true_side", side_evidence=0.4), candidate(5, "back_three_quarter", side_evidence=0.95)],
        {"front": 1, "back": 2, "side": 1},
    )
    analysis = parse_view_analysis(text, 5)
    validate_view_selection(analysis)
    assert (analysis["side"], analysis["side_kind"]) == (4, "true_side")

    text = model_text(
        [candidate(1, "front"), candidate(2, "back"), candidate(3, "front_three_quarter", side_evidence=0.5),
         candidate(4, "back_three_quarter", side_evidence=0.8)],
        {"front": 1, "back": 2, "side": None},
    )
    analysis = parse_view_analysis(text, 4)
    validate_view_selection(analysis)
    assert (analysis["side"], analysis["side_kind"]) == (4, "back_three_quarter")


def test_no_side_evidence():
    analysis = parse_view_analysis(
        model_text([candidate(1, "front"), candidate(2, "back"), candidate(3, "detail")], {"front": 1, "back": 2}), 3,
    )
    validate_view_selection(analysis)
    assert (analysis["side"], analysis["side_kind"]) == (None, "none")


def test_out_of_range_selection_rejected():
    with pytest.raises(ToolError) as exc_info:
        parse_view_analysis(model_text([candidate(1, "front")], {"front": 9}), 2)
    assert exc_info.value.code == "view_analysis_invalid"


def test_text_facts():
    facts = text_facts({"title": "  A  top ", "bullet_points": ["x", "y"], "empty": None, "long": "z" * 400})
    assert facts == {"title": "A top", "bullet_points": "x | y", "long": "z" * 300}


async def test_select_returns_views_and_sends_images_as_data_urls():
    llm = FakeLLM(model_text(
        [candidate(1, "front"), candidate(2, "front_three_quarter", side_evidence=0.6), candidate(3, "back")],
        {"front": 1, "back": 3, "side": 2, "side_kind": "front_three_quarter", "confidence": 0.85, "reason": "ok"},
    ))
    urls = image_urls(3)

    result = await make_tool(llm).execute({"images": urls, "title": "Top"}, SETTINGS)

    assert result.success, result.error_message
    output = result.output
    assert (output["front_url"], output["back_url"], output["side_url"]) == (urls[0], urls[2], urls[1])
    assert (output["side_kind"], output["confidence"], output["reason"]) == ("front_three_quarter", 0.85, "ok")
    assert [c["index"] for c in output["candidates"]] == [1, 2, 3]

    (call,) = llm.calls
    assert call["timeout"] == SETTINGS.timeout
    parts = call["messages"][1]["content"]
    assert '"title": "Top"' in parts[0]["text"]
    image_parts = [p for p in parts if p["type"] == "image_url"]
    assert len(image_parts) == 3
    assert image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_select_reasks_once_when_back_missing():
    llm = FakeLLM([
        model_text([candidate(1, "front"), candidate(2, "detail")], {"front": 1}),
        model_text([candidate(1, "front"), candidate(2, "back")], {"front": 1, "back": 2}),
    ])
    result = await make_tool(llm).execute({"images": image_urls(2)}, SETTINGS)
    assert result.success, result.error_message
    assert len(llm.calls) == 2


async def test_select_fails_without_back_after_reask():
    llm = FakeLLM(model_text([candidate(1, "front"), candidate(2, "detail")], {"front": 1}))
    result = await make_tool(llm).execute({"images": image_urls(2)}, SETTINGS)
    assert (result.success, result.error_code) == (False, "back_view_not_found")
    assert len(llm.calls) == 2


async def test_select_retries_transient_llm_error():
    llm = FakeLLM([
        LLMError("timeout", None, "connection_error"),
        LLMError("busy", 503, "api_error"),
        model_text([candidate(1, "front"), candidate(2, "back")], {"front": 1, "back": 2}),
    ])
    result = await make_tool(llm).execute({"images": image_urls(2)}, SETTINGS)
    assert result.success, result.error_message
    assert len(llm.calls) == 3


async def test_select_llm_error_becomes_tool_error_after_retries():
    llm = FakeLLM(LLMError("boom", 429, "rate_limit_error"))
    result = await make_tool(llm).execute({"images": image_urls(2)}, SETTINGS)
    assert (result.success, result.error_code) == (False, "llm_failed")
    assert len(llm.calls) == 4


async def test_select_does_not_retry_auth_error():
    llm = FakeLLM(LLMError("bad key", 401, "authentication_error"))
    result = await make_tool(llm).execute({"images": image_urls(2)}, SETTINGS)
    assert (result.success, result.error_code) == (False, "llm_failed")
    assert len(llm.calls) == 1


async def test_select_image_download_failure():
    result = await make_tool(FakeLLM(""), status=403).execute({"images": image_urls(2)}, SETTINGS)
    assert (result.success, result.error_code) == (False, "image_download_failed")


async def test_select_requires_at_least_two_images():
    result = await make_tool(FakeLLM("")).execute({"images": image_urls(1)}, SETTINGS)
    assert result.error_code == "invalid_input"


def test_platform_registry_requires_llm():
    with pytest.raises(ValueError, match="llm"):
        platform_tools.build("view_select", ToolDeps(session=None))
    assert isinstance(platform_tools.build("view_select", ToolDeps(session=None, llm=FakeLLM(""))), ViewSelectTool)
