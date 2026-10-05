"""amazon_crawler：页面解析规则与 Tool 行为。HTTP 走 MockTransport，存储用假实现，不打真实网络。"""

from types import SimpleNamespace

import httpx
import pytest

from platforms.tools import ToolDeps, ToolSettings, platform_tools
from platforms.tools.amazon_crawler_tool import AmazonCrawlerTool
from platforms.tools.amazon_page import PageImage, parse_product_page

SETTINGS = ToolSettings(timeout=5.0, trace_id="trace-1")

FACTS_LAYOUT = """
<html><body>
<span id="productTitle">  Women Summer Tops  </span>
<input type="hidden" id="ASIN" value="B0TEST0001">
<div id="productFactsDesktopExpander">
  <div class="a-fixed-left-grid"><span>Fabric type</span><span>Cotton</span></div>
  <h3 class="product-facts-title">About this item</h3>
  <ul>
    <li><span class="a-list-item">&#10022;Material: soft &amp; breathable</span></li>
    <li><span class="a-list-item">Feature: puff <b>sleeves</b></span></li>
    <li><span class="a-list-item">Feature: puff sleeves</span></li>
  </ul>
</div>
<div id="productDescription_feature_div">
  <h2>Product Description</h2>
  <div id="productDescription"><!-- c --><p><span>Line one.</span></p><p>Line two<br>continued</p>
  <style>#productDescription { color: red; }</style></div>
</div>
</body></html>
"""

LEGACY_LAYOUT = """
<html><body>
<span id="productTitle">Legacy Dress</span>
<div id="feature-bullets"><ul>
  <li><span class="a-list-item">Make sure this fits by entering your model number.</span></li>
  <li><span class="a-list-item">Bullet A</span></li>
  <li>Bullet B<img src="x.png"></li>
</ul></div>
<div id="productDescription"><p>  </p></div>
<div id="aplusBrandStory_feature_div"><div id="aplus"><h2>From the brand</h2><p>Brand story</p></div></div>
<div id="aplus_feature_div"><div>
  <h2>Product description</h2>
  <div><h3>Brand Tops</h3><p>The video showcases the product in use.</p><span>Merchant Video</span></div>
  <div><p>Perfect for daily wear.</p><div>Previous page</div><div>2</div><div>Add to Cart</div></div>
  <script>var x = "ignored";</script>
  <h3>More Recommendations</h3><p>Other product should be excluded</p>
</div></div>
</body></html>
"""

IMAGES_SCRIPT = (
    """<script>var data = {'colorImages': { 'initial': A.$.parseJSON('[{"hiRes":"https://m.media-amazon.com/images/I/main._AC_SL1500_.jpg","large":"https://m.media-amazon.com/images/I/main._AC_.jpg","variant":"MAIN"},"""
    """{"hiRes":null,"large":"https://m.media-amazon.com/images/I/pt1._AC_.jpg","variant":"PT01","alt":"Women\\'s top"}]')}, 'colorToAsin': {}};</script>"""
)

CAPTCHA_PAGE = "<html><body><h4>Enter the characters you see below</h4></body></html>"
INTERSTITIAL_PAGE = "<html><body><h4>Click the button below to continue shopping</h4></body></html>"


class FakeStorage:
    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}

    def upload(self, key, data, acl=None):
        self.uploaded[key] = data
        return SimpleNamespace(key=key, url=f"https://cdn.test/{key}")


def make_tool(storage: FakeStorage, pages: dict[str, httpx.Response | list[httpx.Response]]) -> AmazonCrawlerTool:
    """pages 的值为列表时按顺序依次返回，用来模拟「先失败后成功」；requests 记录每个 URL 的请求次数。"""
    requests: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests[url] = requests.get(url, 0) + 1
        response = pages.get(url, httpx.Response(404))
        return response.pop(0) if isinstance(response, list) else response

    tool = AmazonCrawlerTool(storage=storage, transport=httpx.MockTransport(handler))
    tool.retry_delays = (0, 0)
    tool.requests = requests
    return tool


def test_parse_facts_layout():
    page = parse_product_page(FACTS_LAYOUT)
    assert page.asin == "B0TEST0001"
    assert page.title == "Women Summer Tops"
    assert page.bullet_points == ["\u2726Material: soft & breathable", "Feature: puff sleeves"]
    assert page.description == "Line one.\nLine two\ncontinued"
    assert page.images == []


def test_parse_legacy_bullets_and_aplus_fallback():
    page = parse_product_page(LEGACY_LAYOUT)
    assert page.bullet_points == ["Bullet A", "Bullet B"]
    assert page.description == "Brand Tops\nPerfect for daily wear."


def test_parse_images_main_and_gallery():
    assert parse_product_page(FACTS_LAYOUT + IMAGES_SCRIPT).images == [
        PageImage("MAIN", "https://m.media-amazon.com/images/I/main._AC_SL1500_.jpg"),
        PageImage("PT01", "https://m.media-amazon.com/images/I/pt1._AC_.jpg"),
    ]


def test_bullets_capped_at_ten():
    items = "".join(f'<li><span class="a-list-item">Bullet {i}</span></li>' for i in range(15))
    page = parse_product_page(f'<div id="feature-bullets"><ul>{items}</ul></div>')
    assert page.bullet_points == [f"Bullet {i}" for i in range(10)]


async def test_scrape_returns_content_and_stores_images():
    storage = FakeStorage()
    tool = make_tool(storage, {
        "https://www.amazon.com/dp/B0TEST0001": httpx.Response(200, text=FACTS_LAYOUT + IMAGES_SCRIPT),
        "https://m.media-amazon.com/images/I/main._AC_SL1500_.jpg": httpx.Response(200, content=b"main"),
        "https://m.media-amazon.com/images/I/pt1._AC_.jpg": httpx.Response(200, content=b"pt1"),
    })

    result = await tool.execute({"asin": "b0test0001"}, SETTINGS)

    assert result.success, result.error_message
    output = result.output
    assert (output["asin"], output["title"]) == ("B0TEST0001", "Women Summer Tops")
    assert len(output["bullet_points"]) == 2
    assert output["description"] == "Line one.\nLine two\ncontinued"
    assert output["main_image"] == {
        "variant": "MAIN",
        "source_url": "https://m.media-amazon.com/images/I/main._AC_SL1500_.jpg",
        "key": "amazon/B0TEST0001/01_MAIN.jpg",
        "url": "https://cdn.test/amazon/B0TEST0001/01_MAIN.jpg",
    }
    assert [image["key"] for image in output["gallery_images"]] == ["amazon/B0TEST0001/02_PT01.jpg"]
    assert storage.uploaded == {
        "amazon/B0TEST0001/01_MAIN.jpg": b"main",
        "amazon/B0TEST0001/02_PT01.jpg": b"pt1",
    }


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(200, text=CAPTCHA_PAGE), "amazon_blocked"),
        (httpx.Response(200, text=INTERSTITIAL_PAGE), "amazon_blocked"),
        (httpx.Response(200, text="<html><body><p>nothing</p></body></html>"), "no_product_content"),
        (httpx.Response(404), "product_not_found"),
        (httpx.Response(503), "amazon_http_error"),
    ],
)
async def test_scrape_business_failures(response, code):
    url = "https://www.amazon.com/dp/B0TEST0001"
    tool = make_tool(FakeStorage(), {url: response})
    result = await tool.execute({"asin": "B0TEST0001"}, SETTINGS)
    assert (result.success, result.error_code) == (False, code)
    # 被拦截、上游报错重试 2 次；商品不存在、页面无内容不重试
    retried = code in ("amazon_blocked", "amazon_http_error")
    assert tool.requests[url] == (3 if retried else 1)


async def test_scrape_retries_until_page_available():
    url = "https://www.amazon.com/dp/B0TEST0001"
    tool = make_tool(FakeStorage(), {
        url: [httpx.Response(200, text=INTERSTITIAL_PAGE), httpx.Response(200, text=FACTS_LAYOUT)],
    })
    result = await tool.execute({"asin": "B0TEST0001"}, SETTINGS)
    assert result.success, result.error_message
    assert tool.requests[url] == 2


async def test_scrape_image_download_failure():
    tool = make_tool(FakeStorage(), {
        "https://www.amazon.com/dp/B0TEST0001": httpx.Response(200, text=FACTS_LAYOUT + IMAGES_SCRIPT),
    })
    result = await tool.execute({"asin": "B0TEST0001"}, SETTINGS)
    assert (result.success, result.error_code) == (False, "image_download_failed")
    assert tool.requests["https://m.media-amazon.com/images/I/pt1._AC_.jpg"] == 3


async def test_scrape_rejects_invalid_asin():
    result = await make_tool(FakeStorage(), {}).execute({"asin": "not-an-asin"}, SETTINGS)
    assert result.error_code == "invalid_input"


def test_platform_registry_requires_storage():
    with pytest.raises(ValueError, match="storage"):
        platform_tools.build("amazon_crawler", ToolDeps(session=None))
    assert isinstance(platform_tools.build("amazon_crawler", ToolDeps(session=None, storage=FakeStorage())), AmazonCrawlerTool)
