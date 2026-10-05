"""从同一商品的多张图中识别正面、背面、侧面图。

视觉模型给每张候选图标注视角，再由确定性规则挑选正面、背面；侧面优先标准侧面，其次选侧面证据最多的斜侧面。
"""

import asyncio
import base64
import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field, HttpUrl

from platforms.llm import AsyncLLMClient, LLMError
from platforms.tools.amazon_page import clean_text
from platforms.tools.base import (
    Tool,
    ToolError,
    ToolSettings,
    logger,
    retry_async,
)

VIEW_INSTRUCTION = """You select factual garment references for a fixed dummy front/side/back try-on workflow.
All candidate images come from one Feishu Amazon SKU record, but may contain front, back, exact side, front three-quarter, back three-quarter, detail, duplicate, size-chart, lifestyle, another colorway, or another product.

Return JSON only in this exact shape:
{"candidates":[{"index":1,"view":"front|back|true_side|front_three_quarter|back_three_quarter|detail|other|uncertain","confidence":0.00,"same_product":true,"same_color":true,"side_evidence":0.00,"visible_side_facts":"short English facts","reason":"short Chinese reason"}],"selection":{"front":1,"back":2,"side":3,"side_kind":"true_side|front_three_quarter|back_three_quarter|none","confidence":0.00,"reason":"short Chinese reason"}}

Selection rules:
1. Choose one reliable FRONT and one reliable BACK of the same sellable product and exact color. Never invent an unseen back. A catalogue photo that visibly shows the garment's back remains valid BACK evidence even when the model is turned slightly rather than standing at a mathematically exact 180-degree angle. Always populate selection.front and selection.back when such evidence exists; do not leave either field null merely because the view is mildly oblique.
2. For SIDE, first prefer a true near-90-degree side image.
3. If no true side exists, select the best front- or back-three-quarter image when it visibly proves useful side facts such as side seam, side slit, front/back hem height relationship, sleeve/cuff profile, garment thickness, lateral silhouette, waist/hip connection, or drape. A useful 30-70 degree oblique image is valid side evidence and must not be discarded merely because it is not a strict side view.
4. side_evidence measures how much factual side construction is visible, not how close the camera angle is to 90 degrees.
5. A model-worn image is acceptable when the garment is clear, but the model's body, hands, pose, hair, jewelry, pants, and accessories are not product facts.
6. same_product and same_color are mandatory for every selected image. Exclude other colorways, styling pieces, details without enough structure, size charts, and unrelated images.
7. For a set, selected views must show the complete sold set. If no useful side evidence exists, side must be null and side_kind must be none.
8. Do not mistake pose, hand placement, occlusion, or incidental folds for side slits or construction details."""

VALID_VIEWS = {
    "front", "back", "true_side", "front_three_quarter", "back_three_quarter",
    "detail", "other", "uncertain",
}
SIDE_VIEWS = {"true_side", "front_three_quarter", "back_three_quarter"}
ROLE_VIEWS = {"front": ("front", "front_three_quarter"), "back": ("back", "back_three_quarter")}
ROLE_NAMES = {"front": "正面", "back": "背面", "side": "侧面"}
REVIEW_RETRY_CODES = {"front_view_not_found", "back_view_not_found", "front_view_mismatch", "back_view_mismatch"}


class ViewSelectInput(BaseModel):
    images: list[HttpUrl] = Field(min_length=2)     # 同一商品的候选图，顺序即编号（从 1 开始）
    title: str | None = None
    bullet_points: list[str] = []
    description: str | None = None


class ViewCandidate(BaseModel):
    index: int
    url: str
    view: str
    confidence: float
    side_evidence: float
    same_product: bool
    same_color: bool
    visible_side_facts: str
    reason: str


class ViewSelectOutput(BaseModel):
    front_url: str
    back_url: str
    side_url: str | None
    side_kind: str              # true_side | front_three_quarter | back_three_quarter | none
    confidence: float
    reason: str
    candidates: list[ViewCandidate]


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


def text_facts(fields: dict[str, Any]) -> dict[str, str]:
    facts: dict[str, str] = {}
    for name, value in fields.items():
        if isinstance(value, list):
            value = " | ".join(str(v) for v in value)
        if isinstance(value, dict) or value is None:
            continue
        text = clean_text(str(value))
        if text:
            facts[str(name)] = text[:300]
    return facts


def parse_view_analysis(text: str, count: int) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ToolError("view_analysis_invalid", "商品视角识别未返回 JSON")
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ToolError("view_analysis_invalid", f"商品视角识别返回的 JSON 无法解析：{exc}") from exc

    candidates: dict[int, dict[str, Any]] = {}
    for item in raw.get("candidates") if isinstance(raw.get("candidates"), list) else []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if not 1 <= index <= count:
            continue
        view = str(item.get("view") or "uncertain").strip().lower()
        candidates[index] = {
            "view": view if view in VALID_VIEWS else "uncertain",
            "confidence": _clamp(item.get("confidence")),
            "side_evidence": _clamp(item.get("side_evidence")),
            "same_product": bool(item.get("same_product", False)),
            "same_color": bool(item.get("same_color", False)),
            "visible_side_facts": str(item.get("visible_side_facts") or "").strip()[:220],
            "reason": str(item.get("reason") or "").strip()[:180],
        }
    selection = raw.get("selection") if isinstance(raw.get("selection"), dict) else {}

    def selected_index(name: str) -> int | None:
        value = selection.get(name)
        # 模型偶尔标对了所有候选却漏填某个选择项，交给下方的确定性规则补选
        if value in (None, "", 0):
            return None
        try:
            index = int(value)
        except (TypeError, ValueError):
            raise ToolError("view_analysis_invalid", f"商品视角识别未提供有效的{ROLE_NAMES[name]}图片编号") from None
        if not 1 <= index <= count:
            raise ToolError("view_analysis_invalid", f"商品视角识别返回的{ROLE_NAMES[name]}图片编号超出范围")
        return index

    selected: dict[str, Any] = {
        "candidates": candidates,
        "front": selected_index("front"),
        "back": selected_index("back"),
        "side": selected_index("side"),
        "side_kind": str(selection.get("side_kind") or "none").strip().lower(),
        "confidence": _clamp(selection.get("confidence")),
        "reason": str(selection.get("reason") or "").strip()[:240],
    }

    def resolve_required_view(role: str, excluded: set) -> int | None:
        accepted = ROLE_VIEWS[role]
        current = selected.get(role)
        if current and current not in excluded:
            candidate = candidates.get(current, {})
            if candidate.get("view") in accepted and candidate.get("same_product") and candidate.get("same_color"):
                return current
        ranked = [
            index for index, candidate in candidates.items()
            if index not in excluded
            and candidate["view"] in accepted
            and candidate["same_product"]
            and candidate["same_color"]
        ]
        return max(
            ranked,
            key=lambda index: (candidates[index]["view"] == accepted[0], candidates[index]["confidence"]),
            default=None,
        )

    # 轻微斜角的目录图仍是有效的正/背面证据：优先标准视角，但不因模型标成 three_quarter 就判定缺失
    selected["front"] = resolve_required_view("front", set())
    selected["back"] = resolve_required_view("back", {selected["front"]} if selected["front"] else set())
    return selected


def validate_view_selection(analysis: dict[str, Any]) -> None:
    # 置信度只用于候选排序，不作为硬性拦截：Amazon 图常是模特上身或斜角，但仍是有效证据
    for role in ("front", "back"):
        candidate = analysis["candidates"].get(analysis[role], {})
        if candidate.get("view") not in ROLE_VIEWS[role]:
            raise ToolError(f"{role}_view_not_found", f"未识别到可靠{ROLE_NAMES[role]}图片")
        if not candidate.get("same_product") or not candidate.get("same_color"):
            raise ToolError(f"{role}_view_mismatch", f"{ROLE_NAMES[role]}图片与当前商品或颜色不一致")

    def usable_side(index: int | None) -> bool:
        if not index or index in {analysis["front"], analysis["back"]}:
            return False
        candidate = analysis["candidates"].get(index, {})
        return bool(candidate.get("view") in SIDE_VIEWS and candidate.get("same_product") and candidate.get("same_color"))

    side = analysis.get("side")
    if not usable_side(side):
        side = max(
            [index for index in analysis["candidates"] if usable_side(index)],
            key=lambda index: (
                analysis["candidates"][index].get("view") == "true_side",
                analysis["candidates"][index].get("side_evidence", 0),
                analysis["candidates"][index].get("confidence", 0),
            ),
            default=None,
        )
    analysis["side"] = side
    analysis["side_kind"] = analysis["candidates"].get(side, {}).get("view", "none") if side else "none"


def _image_mime(content: bytes, content_type: str) -> str:
    """对象存储常以 application/octet-stream 返回图片，按文件头识别，识别不了再用响应头。"""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    mime = content_type.split(";")[0].strip()
    return mime if mime.startswith("image/") else "image/jpeg"


class ViewSelectTool(Tool[ViewSelectInput, ViewSelectOutput]):
    """瞬时网络错误按 retry_delays 重试；正/背面漏判时重新识别一次，仍缺失才返回 ToolError。

    图片由本 Tool 下载后以 data URL 发给模型：海外模型服务直连国内对象存储容易下载超时。
    """

    name = "view_select"
    input_model = ViewSelectInput
    output_model = ViewSelectOutput
    retry_delays: tuple[float, ...] = (2, 5, 10)

    def __init__(self, *, llm: AsyncLLMClient, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._llm = llm
        self._transport = transport

    async def run(self, payload: ViewSelectInput, settings: ToolSettings) -> ViewSelectOutput:
        urls = [str(url) for url in payload.images]
        data_urls = await self._download_images(urls, settings)
        facts = text_facts({
            "title": payload.title,
            "bullet_points": payload.bullet_points,
            "product_description": payload.description,
        })
        content: list[dict[str, Any]] = [
            {"type": "text", "text": "Product facts:\n" + json.dumps(facts, ensure_ascii=False)},
        ]
        for index, data_url in enumerate(data_urls, start=1):
            content.append({"type": "text", "text": f"Candidate image {index}:"})
            content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "high"}})
        messages = [
            {"role": "system", "content": VIEW_INSTRUCTION},
            {"role": "user", "content": content},
        ]

        analysis = await self._analyze(messages, len(urls), settings)
        try:
            validate_view_selection(analysis)
        except ToolError as exc:
            # 视觉模型偶尔漏判明显的正/背面：仅此情况重新识别一次，真正缺背面的商品第二次仍会失败
            if exc.code not in REVIEW_RETRY_CODES:
                raise
            logger.warning("[%s] 正/背面识别缺失，重新识别一次：%s", settings.trace_id, exc.message)
            analysis = await self._analyze(messages, len(urls), settings)
            validate_view_selection(analysis)

        side = analysis["side"]
        return ViewSelectOutput(
            front_url=urls[analysis["front"] - 1],
            back_url=urls[analysis["back"] - 1],
            side_url=urls[side - 1] if side else None,
            side_kind=analysis["side_kind"],
            confidence=analysis["confidence"],
            reason=analysis["reason"],
            candidates=[
                ViewCandidate(index=index, url=urls[index - 1], **candidate)
                for index, candidate in sorted(analysis["candidates"].items())
            ],
        )

    async def _analyze(self, messages: list[dict], count: int, settings: ToolSettings) -> dict[str, Any]:
        try:
            response = await retry_async(
                lambda: self._llm.chat.completions.create(messages=messages, timeout=settings.timeout),
                delays=self.retry_delays, retry_if=_is_transient_llm_error,
                label="商品视角识别", trace_id=settings.trace_id,
            )
        except LLMError as exc:
            raise ToolError("llm_failed", f"商品视角识别调用失败：{exc.message}") from exc
        return parse_view_analysis(response.choices[0].message.content or "", count)

    async def _download_images(self, urls: list[str], settings: ToolSettings) -> list[str]:
        async def download_all() -> list[httpx.Response]:
            responses = await asyncio.gather(*(http.get(url) for url in urls))
            for response in responses:
                response.raise_for_status()
            return responses

        async with httpx.AsyncClient(
            timeout=settings.timeout, follow_redirects=True, transport=self._transport,
        ) as http:
            try:
                responses = await retry_async(
                    download_all, delays=self.retry_delays, retry_if=_is_transient_http_error,
                    label="候选图下载", trace_id=settings.trace_id,
                )
            except httpx.HTTPError as exc:
                raise ToolError("image_download_failed", f"候选图下载失败：{type(exc).__name__}: {exc}") from exc
        return [
            f"data:{_image_mime(r.content, r.headers.get('content-type', ''))};base64,"
            f"{base64.b64encode(r.content).decode()}"
            for r in responses
        ]


def _is_transient_http_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


def _is_transient_llm_error(exc: Exception) -> bool:
    if not isinstance(exc, LLMError):
        return False
    return exc.error_type in ("connection_error", "rate_limit_error") or (exc.status_code or 0) >= 500
