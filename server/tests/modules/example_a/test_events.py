"""Verify the synchronous cross-module event demo without requiring PostgreSQL."""

from modules.example_a.api import ItemCreate, create_item
from modules.example_a.contract import ItemCreated
from modules.example_b import service as example_b_service
from platforms import events
from platforms.config import Settings
from platforms.gateway.app import create_app


class FakeSession:
    def add(self, item) -> None:
        self.item = item

    async def flush(self) -> None:
        self.item.id = 42

    async def commit(self) -> None:
        assert example_b_service.list_received() == []


async def test_create_item_is_received_by_example_b_synchronously():
    events.clear()
    example_b_service.clear_received()
    create_app(Settings(enabled_modules=["example_b"]))
    try:
        await create_item(ItemCreate(name="同步抵达"), FakeSession())
        assert example_b_service.list_received() == [ItemCreated(item_id=42, name="同步抵达")]
    finally:
        events.clear()
        example_b_service.clear_received()