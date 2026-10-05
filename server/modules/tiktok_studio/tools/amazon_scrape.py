"""按 ASIN 抓取 Amazon 商品详情：标题、About this item 亮点、产品描述，主图副图转存到对象存储。"""

import asyncio
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from modules.tiktok_studio.tools.amazon_page import (
    PageImage,
    detect_blocked_page,
    parse_product_page,
)
from modules.tiktok_studio.tools.base import Tool, ToolError, ToolSettings, retry_async
from platforms.storage import ObjectStorage

AMAZON_DOMAIN = "www.amazon.com"
STORAGE_PREFIX = "tiktok_studio/amazon"
# 网络失败、被拦截、上游报错可能是瞬时的；商品不存在、页面无内容重试也没用
RETRYABLE_CODES = {"amazon_fetch_failed", "amazon_http_error", "amazon_blocked", "image_download_failed"}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # httpx 默认还带 br、zstd，Amazon 会因此返回「continue shopping」拦截页
    "Accept-Encoding": "gzip, deflate",
}


class AmazonScrapeInput(BaseModel):
    asin: str = Field(pattern=r"^([Bb]0[A-Za-z0-9]{8}|\d{9}[\dXx])$")


class ProductImage(BaseModel):
    variant: str                # MAIN 为主图，PT01、PT02… 为副图
    source_url: str             # Amazon 原图地址
    key: str                    # 对象存储 key
    url: str | None             # 对象存储公开地址；存储 ACL 为 private 时为 None


class AmazonScrapeOutput(BaseModel):
    asin: str
    product_url: str
    title: str | None
    bullet_points: list[str]    # About this item，最多 10 条
    description: str | None
    main_image: ProductImage | None
    gallery_images: list[ProductImage]


class AmazonScrapeTool(Tool[AmazonScrapeInput, AmazonScrapeOutput]):
    """商品页请求失败、被拦截时按 retry_delays 重试，耗尽后以 ToolError 返回。"""

    name = "amazon_scrape"
    input_model = AmazonScrapeInput
    output_model = AmazonScrapeOutput
    retry_delays: tuple[float, ...] = (3, 6)

    def __init__(self, *, storage: ObjectStorage, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._storage = storage
        self._transport = transport

    async def run(self, payload: AmazonScrapeInput, settings: ToolSettings) -> AmazonScrapeOutput:
        asin = payload.asin.upper()
        product_url = f"https://{AMAZON_DOMAIN}/dp/{asin}"
        async with httpx.AsyncClient(
            headers=REQUEST_HEADERS, timeout=settings.timeout, follow_redirects=True, transport=self._transport,
        ) as http:
            page_html = await retry_async(
                lambda: self._fetch_page(http, product_url),
                delays=self.retry_delays, retry_if=_is_retryable, label=f"商品页 {asin}", trace_id=settings.trace_id,
            )
            page = parse_product_page(page_html)
            if not page.title and not page.bullet_points and not page.description:
                raise ToolError("no_product_content", f"商品页 {product_url} 未解析到标题、亮点或描述")
            images = await asyncio.gather(*(
                self._store_image(http, asin, index, image, product_url, settings)
                for index, image in enumerate(page.images, start=1)
            ))

        main = next((image for image in images if image.variant == "MAIN"), None)
        return AmazonScrapeOutput(
            asin=page.asin or asin,
            product_url=product_url,
            title=page.title,
            bullet_points=page.bullet_points,
            description=page.description,
            main_image=main,
            gallery_images=[image for image in images if image is not main],
        )

    @staticmethod
    async def _fetch_page(http: httpx.AsyncClient, url: str) -> str:
        try:
            response = await http.get(url)
        except httpx.HTTPError as exc:
            raise ToolError("amazon_fetch_failed", f"商品页请求失败 {url}：{type(exc).__name__}: {exc}") from exc
        if response.status_code == 404:
            raise ToolError("product_not_found", f"商品不存在：{url}")
        if response.status_code >= 400:
            raise ToolError("amazon_http_error", f"商品页返回 HTTP {response.status_code}：{url}")
        blocked = detect_blocked_page(response.text)
        if blocked:
            raise ToolError("amazon_blocked", f"商品页被 Amazon 拦截：{blocked}")
        return response.text

    async def _store_image(
        self, http: httpx.AsyncClient, asin: str, index: int, image: PageImage, referer: str, settings: ToolSettings,
    ) -> ProductImage:
        async def download() -> bytes:
            try:
                response = await http.get(image.url, headers={"Referer": referer})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ToolError(
                    "image_download_failed", f"商品图下载失败 {image.url}：{type(exc).__name__}: {exc}",
                ) from exc
            return response.content

        content = await retry_async(
            download, delays=self.retry_delays, retry_if=_is_retryable,
            label=f"商品图 {image.url}", trace_id=settings.trace_id,
        )
        suffix = PurePosixPath(urlparse(image.url).path).suffix or ".jpg"
        key = f"{STORAGE_PREFIX}/{asin}/{index:02d}_{image.variant or 'IMG'}{suffix}"
        record = await asyncio.to_thread(self._storage.upload, key, content)
        return ProductImage(variant=image.variant, source_url=image.url, key=key, url=record.url)


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, ToolError) and exc.code in RETRYABLE_CODES
