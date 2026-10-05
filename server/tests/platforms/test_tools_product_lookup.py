"""product_lookup：按货号检索 mock 数据集。"""

from platforms.tools import ToolDeps, ToolSettings, platform_tools
from platforms.tools.product_lookup_tool import ProductLookupTool

SETTINGS = ToolSettings(timeout=5.0, trace_id="trace-1")


async def test_lookup_returns_all_records_of_sku():
    result = await ProductLookupTool().execute({"sku": " wtk9167 "}, SETTINGS)

    assert result.success, result.error_message
    assert result.output["sku"] == "WTK9167"
    items = result.output["items"]
    assert len(items) > 1
    assert {item["sku"] for item in items} == {"WTK9167"}
    assert set(items[0]) == {"id", "sku", "asin", "color", "store", "pid", "category"}
    assert items[0]["asin"]


async def test_lookup_unknown_sku_fails():
    result = await ProductLookupTool().execute({"sku": "NOPE0000"}, SETTINGS)
    assert (result.success, result.error_code) == (False, "product_not_found")


async def test_lookup_rejects_empty_sku():
    result = await ProductLookupTool().execute({"sku": ""}, SETTINGS)
    assert result.error_code == "invalid_input"


def test_platform_registry_builds_product_lookup():
    assert isinstance(platform_tools.build("product_lookup", ToolDeps(session=None)), ProductLookupTool)
