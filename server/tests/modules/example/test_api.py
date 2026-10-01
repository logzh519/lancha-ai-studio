"""模块测试示例：模块自己的测试放在 tests/modules/<模块名>/ 下。"""

import pytest

from modules.example import contract, service

pytestmark = pytest.mark.db


async def test_create_then_list(session):
    await service.create_item(session, "第一条")
    await service.create_item(session, "第二条")
    items = await service.list_items(session, limit=10)
    assert [item.name for item in items] == ["第二条", "第一条"]


async def test_contract_returns_dto_not_orm(session):
    item = await service.create_item(session, "对外暴露的条目")
    view = await contract.get_item(session, item.id)
    assert view == contract.ItemView(id=item.id, name="对外暴露的条目")


async def test_contract_returns_none_for_missing_item(session):
    assert await contract.get_item(session, 10**9) is None
