"""按产品货号查询关联的 SKU 级商品数据：ASIN、颜色、店铺、PID、类目。

上游 API 尚未提供，_fetch 暂时检索本地 mock 数据集 data/product_lookup_mock.json
（取自飞书「亚马逊SKU级产品信息及三视图」与「产品母表」，缺失字段为 null）。
接入真实 API 时只替换 _fetch，输入输出契约不变。
"""

import json
from functools import cache
from pathlib import Path

from pydantic import BaseModel, Field

from platforms.tools.base import Tool, ToolError, ToolSettings

MOCK_DATA = Path(__file__).with_name("data") / "product_lookup_mock.json"


class ProductLookupInput(BaseModel):
    sku: str = Field(min_length=1, max_length=64)     # 产品货号，如 WTK9167；大小写不敏感


class ProductRecord(BaseModel):
    id: int
    sku: str
    asin: str | None
    color: str | None
    store: str | None
    pid: str | None
    category: str | None


class ProductLookupOutput(BaseModel):
    sku: str
    items: list[ProductRecord]      # 同一货号下的全部 SKU 记录（不同颜色、店铺）


@cache
def _load_mock() -> tuple[ProductRecord, ...]:
    return tuple(ProductRecord(**row) for row in json.loads(MOCK_DATA.read_text(encoding="utf-8")))


class ProductLookupTool(Tool[ProductLookupInput, ProductLookupOutput]):
    """货号查不到时抛 ToolError("product_not_found")。"""

    name = "product_lookup"
    input_model = ProductLookupInput
    output_model = ProductLookupOutput

    async def run(self, payload: ProductLookupInput, settings: ToolSettings) -> ProductLookupOutput:
        sku = payload.sku.strip().upper()
        items = await self._fetch(sku, settings)
        if not items:
            raise ToolError("product_not_found", f"货号 {sku} 没有关联的商品数据")
        return ProductLookupOutput(sku=sku, items=items)

    async def _fetch(self, sku: str, settings: ToolSettings) -> list[ProductRecord]:
        return [record for record in _load_mock() if record.sku == sku]
