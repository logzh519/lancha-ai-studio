import pytest

from modules.tiktok import contract, service

pytestmark = pytest.mark.db


async def test_create_then_list(session):
    await service.create_account(session, "第一个")
    await service.create_account(session, "第二个")
    accounts = await service.list_accounts(session, limit=10)
    assert [account.name for account in accounts] == ["第二个", "第一个"]


async def test_contract_returns_dto_not_orm(session):
    account = await service.create_account(session, "对外暴露的账号")
    view = await contract.get_account(session, account.id)
    assert view == contract.AccountView(id=account.id, name="对外暴露的账号")


async def test_contract_returns_none_for_missing_account(session):
    assert await contract.get_account(session, 10**9) is None
