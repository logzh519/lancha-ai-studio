"""用商品的正面、背面、侧面参考图生成三视图，结果转存到对象存储。

上衣、套装、连衣裙/连体衣套到固定木质假人模板上生成试穿三视图；下装生成无人物的单品三视图。
参考图由上游 view_select 选定，本 Tool 只负责形态识别、细节锁定、拼提示词与生图。
"""

import asyncio
import base64
import io
import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from PIL import Image
from pydantic import BaseModel, Field, HttpUrl, model_validator

from modules.tiktok_studio.tools import three_view_prompts as prompts
from platforms.llm import AsyncLLMClient, LLMError
from platforms.storage import ObjectStorage
from platforms.tools.base import Tool, ToolError, ToolSettings, logger, retry_async

ASSET_DIR = Path(__file__).with_name("three_view_assets")
TEMPLATES = {
    "v2": ASSET_DIR / "dummy_triptych_v2.jpg",
    "v3": ASSET_DIR / "dummy_triptych_v3.jpg",
}
IMAGE_MODEL = "gpt-image-2"
IMAGE_QUALITY = "medium"
PRODUCT_ONLY_SIZE = "1536x1024"
CLASSIFY_THRESHOLD = 0.78
DETAIL_THRESHOLD = 0.85
STORAGE_PREFIX = "three_view"

Category = Literal["upper", "bottom", "set", "one_piece"]
SideKind = Literal["true_side", "front_three_quarter", "back_three_quarter", "none"]


class ThreeViewGenInput(BaseModel):
    asin: str = Field(pattern=r"^([Bb]0[A-Za-z0-9]{8}|\d{9}[\dXx])$")
    product_code: str = ""
    color: str = ""
    title: str | None = None
    bullet_points: list[str] = []
    description: str | None = None
    front_url: HttpUrl
    back_url: HttpUrl
    side_url: HttpUrl | None = None
    side_kind: SideKind = "none"
    generation_type: Category | Literal["auto"] = "auto"     # auto 时先由视觉模型识别商品形态
    # 生图尺寸（宽x高），同时作用于假人模板和下装单品；缺省时假人按模板 16 对齐、单品为 1536x1024
    size: str | None = Field(default=None, pattern=r"^\d+x\d+$")

    @model_validator(mode="after")
    def _check_side(self) -> "ThreeViewGenInput":
        if (self.side_url is None) != (self.side_kind == "none"):
            raise ValueError("side_url 与 side_kind 必须同时提供或同时缺省")
        return self


class Classification(BaseModel):
    category: Category | Literal["uncertain"]
    confidence: float
    reason: str


class DetailLock(BaseModel):
    details: list[str]
    mannequin_limb_required: bool
    limb_reason: str
    error: str | None = None    # 识别失败时不阻断生图，只记下原因


class ThreeViewGenOutput(BaseModel):
    generation_type: Category
    workflow: Literal["dummy_tryon", "product_only"]
    template: Literal["v2", "v3"] | None
    size: str
    prompt: str
    classification: Classification | None
    detail_lock: DetailLock | None
    image_key: str
    image_url: str | None


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


def product_facts(payload: ThreeViewGenInput) -> dict[str, str]:
    facts: dict[str, str] = {}
    for name, value in (
        ("title", payload.title),
        ("bullet_points", " | ".join(payload.bullet_points)),
        ("product_description", payload.description),
    ):
        text = " ".join((value or "").split())
        if text:
            facts[name] = text[:300]
    return facts


def parse_classification(raw: dict[str, Any]) -> Classification:
    category = str(raw.get("category") or "uncertain").strip().lower()
    if category not in {"upper", "bottom", "set", "one_piece"}:
        category = "uncertain"
    return Classification(
        category=category, confidence=_clamp(raw.get("confidence")), reason=str(raw.get("reason") or "").strip()[:180],
    )


def parse_detail_lock(raw: dict[str, Any]) -> DetailLock:
    items = raw.get("critical_details") if isinstance(raw.get("critical_details"), list) else []
    details = [
        str(item.get("fact")).strip()[:240]
        for item in items
        if isinstance(item, dict) and str(item.get("fact") or "").strip() and _clamp(item.get("confidence")) >= DETAIL_THRESHOLD
    ]
    if not details:
        raise ToolError("no_critical_details", "未识别到置信度足够的商品关键细节")
    return DetailLock(
        details=details[:12],
        mannequin_limb_required=str(raw.get("mannequin_limb_support") or "").strip().lower() == "required",
        limb_reason=str(raw.get("limb_reason") or "").strip()[:180],
    )


def _image_mime(content: bytes) -> str:
    if content.startswith(b"\x89PNG"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return "image/jpeg"


def prepare_template(template_path: Path, requested_size: str | None) -> tuple[bytes, str]:
    """把固定假人模板居中补白到宽高都能被 16 整除的画布；禁止裁剪或缩放假人。"""
    with Image.open(template_path) as image:
        source = image.copy()
    if requested_size:
        target_width, target_height = map(int, requested_size.split("x"))
        if target_width % 16 or target_height % 16:
            raise ToolError("invalid_size", f"图片尺寸 {requested_size} 无效：宽高都必须能被 16 整除")
    else:
        target_width = (source.width + 15) // 16 * 16
        target_height = (source.height + 15) // 16 * 16
    if target_width < source.width or target_height < source.height:
        raise ToolError(
            "invalid_size",
            f"目标尺寸 {target_width}x{target_height} 小于模板 {source.width}x{source.height}，禁止裁剪或缩放固定假人",
        )
    size = f"{target_width}x{target_height}"
    if (target_width, target_height) == source.size:
        return template_path.read_bytes(), size
    if source.mode == "RGBA":
        background: Any = (255, 255, 255, 255)
    elif source.mode == "RGB":
        background = (255, 255, 255)
    elif source.mode == "L":
        background = 255
    else:
        source = source.convert("RGBA")
        background = (255, 255, 255, 255)
    canvas = Image.new(source.mode, (target_width, target_height), background)
    canvas.paste(source, ((target_width - source.width) // 2, (target_height - source.height) // 2))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue(), size


def _image_file(stem: str, content: bytes) -> tuple[str, bytes, str]:
    """multipart 上传用的 (文件名, 内容, MIME)。"""
    mime = _image_mime(content)
    return f"{stem}.{mime.split('/')[1]}", content, mime


def _data_url(content: bytes) -> str:
    return f"data:{_image_mime(content)};base64,{base64.b64encode(content).decode()}"


class ThreeViewGenTool(Tool[ThreeViewGenInput, ThreeViewGenOutput]):
    """视觉识别与图片下载的瞬时故障按 retry_delays 重试，生图按 image_retry_delays 重试。

    商品形态识别不可靠时以 needs_confirmation 失败，交人工确认，不猜类型。
    参考图由本 Tool 下载后发给模型：海外模型服务直连国内对象存储容易下载超时。
    """

    name = "three_view_gen"
    input_model = ThreeViewGenInput
    output_model = ThreeViewGenOutput
    retry_delays: tuple[float, ...] = (2, 5, 10)
    image_retry_delays: tuple[float, ...] = (8,)

    def __init__(
        self, *, llm: AsyncLLMClient, storage: ObjectStorage, transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._llm = llm
        self._storage = storage
        self._transport = transport

    async def run(self, payload: ThreeViewGenInput, settings: ToolSettings) -> ThreeViewGenOutput:
        urls = [str(payload.front_url), str(payload.back_url)] + ([str(payload.side_url)] if payload.side_url else [])
        references = await self._download(urls, settings)
        facts = product_facts(payload)
        layout = prompts.input_layout(payload.side_kind)

        classification = None
        category = payload.generation_type
        if category == "auto":
            classification = await self._classify(facts, references[0], settings)
            if classification.category == "uncertain" or classification.confidence < CLASSIFY_THRESHOLD:
                raise ToolError("needs_confirmation", classification.reason or "商品形态无法可靠确认")
            category = classification.category

        files = [_image_file(role, content) for role, content in zip(("front", "back", "side"), references)]
        detail_lock = None
        if category == "bottom":
            workflow, template, size = "product_only", None, payload.size or PRODUCT_ONLY_SIZE
            prompt = prompts.render_bottom_prompt(payload.product_code, payload.color, payload.asin, layout)
        else:
            workflow, template = "dummy_tryon", "v3" if category == "upper" else "v2"
            detail_lock = await self._lock_details(facts, references, layout, settings)
            prompt = prompts.render_dummy_prompt(
                category, layout, detail_lock.details, payload.side_kind, detail_lock.mannequin_limb_required, template,
            )
            template_image, size = await asyncio.to_thread(prepare_template, TEMPLATES[template], payload.size)
            files.insert(0, _image_file("template", template_image))

        image = await self._generate(prompt, size, files, settings)
        key = f"{STORAGE_PREFIX}/{payload.asin.upper()}/{uuid.uuid4().hex}.png"
        record = await asyncio.to_thread(self._storage.upload, key, image)
        return ThreeViewGenOutput(
            generation_type=category, workflow=workflow, template=template, size=size, prompt=prompt,
            classification=classification, detail_lock=detail_lock, image_key=key, image_url=record.url,
        )

    async def _classify(self, facts: dict[str, str], front: bytes, settings: ToolSettings) -> Classification:
        content = [
            {"type": "text", "text": "Product facts:\n" + json.dumps(facts, ensure_ascii=False)},
            {"type": "image_url", "image_url": {"url": _data_url(front), "detail": "high"}},
        ]
        raw = await self._vision_json("商品形态识别", prompts.CLASSIFY_PRODUCT_INSTRUCTION, content, settings)
        return parse_classification(raw)

    async def _lock_details(
        self, facts: dict[str, str], references: list[bytes], layout: str, settings: ToolSettings,
    ) -> DetailLock:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": "Product facts:\n" + json.dumps(facts, ensure_ascii=False)},
            {"type": "text", "text": f"Confirmed reference order: {layout}."},
        ]
        for role, reference in zip(("FRONT", "BACK", "SIDE"), references):
            content.append({"type": "text", "text": f"Confirmed {role} product reference:"})
            content.append({"type": "image_url", "image_url": {"url": _data_url(reference), "detail": "high"}})
        try:
            raw = await self._vision_json("商品关键细节识别", prompts.DETAIL_LOCK_INSTRUCTION, content, settings)
            return parse_detail_lock(raw)
        except ToolError as exc:
            # 细节锁只是加强约束，缺失时仍按通用规则生图
            logger.warning("[%s] 商品关键细节不可用，按通用规则生图：%s", settings.trace_id, exc.message)
            return DetailLock(details=[], mannequin_limb_required=False, limb_reason="", error=exc.message[:300])

    async def _vision_json(
        self, label: str, instruction: str, content: list[dict[str, Any]], settings: ToolSettings,
    ) -> dict[str, Any]:
        messages = [{"role": "system", "content": instruction}, {"role": "user", "content": content}]
        try:
            response = await retry_async(
                lambda: self._llm.chat.completions.create(messages=messages, temperature=0, timeout=settings.timeout),
                delays=self.retry_delays, retry_if=_is_transient_llm_error, label=label, trace_id=settings.trace_id,
            )
        except LLMError as exc:
            raise ToolError("llm_failed", f"{label}调用失败：{exc.message}") from exc
        match = re.search(r"\{.*\}", response.choices[0].message.content or "", flags=re.DOTALL)
        try:
            raw = json.loads(match.group(0)) if match else None
        except json.JSONDecodeError:
            raw = None
        if not isinstance(raw, dict):
            raise ToolError("llm_invalid_output", f"{label}未返回有效 JSON")
        return raw

    async def _generate(
        self, prompt: str, size: str, files: list[tuple[str, bytes, str]], settings: ToolSettings,
    ) -> bytes:
        try:
            response = await retry_async(
                lambda: self._llm.images.edit(
                    model=IMAGE_MODEL, image=files, prompt=prompt, size=size, quality=IMAGE_QUALITY,
                    timeout=settings.timeout,
                ),
                delays=self.image_retry_delays, retry_if=_is_transient_llm_error,
                label="三视图生图", trace_id=settings.trace_id,
            )
        except LLMError as exc:
            raise ToolError("image_generation_failed", f"三视图生图失败：{exc.message}") from exc
        image = (response.data or [None])[0]
        if image is not None and image.b64_json:
            return base64.b64decode(image.b64_json)
        if image is not None and image.url:
            (content,) = await self._download([image.url], settings)
            return content
        raise ToolError("image_generation_failed", "图片模型未返回图片")

    async def _download(self, urls: list[str], settings: ToolSettings) -> list[bytes]:
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
                    label="图片下载", trace_id=settings.trace_id,
                )
            except httpx.HTTPError as exc:
                raise ToolError("image_download_failed", f"图片下载失败：{type(exc).__name__}: {exc}") from exc
        return [response.content for response in responses]


def _is_transient_http_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


def _is_transient_llm_error(exc: Exception) -> bool:
    if not isinstance(exc, LLMError):
        return False
    return exc.error_type in ("connection_error", "rate_limit_error") or (exc.status_code or 0) >= 500
