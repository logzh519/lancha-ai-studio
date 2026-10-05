"""按货号批量导入商品：同步查询 SKU 记录并入库，Amazon 抓取与三视图识别交给 worker 后台执行。"""

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from modules.tiktok_studio import service, tools
from modules.tiktok_studio.models import ProductMaster

LOOKUP_TIMEOUT = 10.0
SKU_SEPARATORS = re.compile(r"[;；,，\s]+")


@dataclass(frozen=True)
class ImportFailure:
    sku: str
    message: str


@dataclass(frozen=True)
class ImportResult:
    created: list[ProductMaster]
    skipped: int                    # 货号 + ASIN 已存在而跳过的记录数
    failed: list[ImportFailure]


def normalize_skus(raw: list[str]) -> list[str]:
    """按分号、逗号（含全角）和空白拆分，转大写、去重，保持输入顺序。"""
    skus = (sku.upper() for entry in raw for sku in SKU_SEPARATORS.split(entry) if sku)
    return list(dict.fromkeys(skus))


async def import_skus(session: AsyncSession, skus: list[str], created_by: int | None) -> ImportResult:
    lookup = tools.build("product_lookup", tools.ToolDeps(session=session))
    existing = await service.existing_product_keys(session, skus)
    records: list[dict] = []
    skipped = 0
    failed: list[ImportFailure] = []
    for sku in skus:
        result = await lookup.execute(
            {"sku": sku}, tools.ToolSettings(timeout=LOOKUP_TIMEOUT, trace_id=f"product_import:{sku}")
        )
        if not result.success:
            failed.append(ImportFailure(sku, result.error_message or result.error_code or "查询失败"))
            continue
        for item in result.output["items"]:
            key = (item["sku"].upper(), item["asin"])
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            records.append(item)
    created = await service.create_imported_products(session, records, created_by)
    return ImportResult(created, skipped, failed)
