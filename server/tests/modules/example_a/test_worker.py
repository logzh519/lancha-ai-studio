"""示例后台循环：先跑一轮再休眠，收到停机后退出。"""

import asyncio
import logging

import pytest

from modules.example_a import service
from modules.example_a.module import MODULE
from modules.example_a.worker import report_item_count
from platforms.contract import LoopContext

pytestmark = pytest.mark.db


def test_module_declares_report_loop():
    assert [loop.name for loop in MODULE.loops] == ["report_item_count"]


async def test_count_items(session):
    before = await service.count_items(session)
    await service.create_item(session, "计数")
    assert await service.count_items(session) == before + 1


async def test_report_item_count_runs_once_then_stops(db_ready, caplog):
    stopping = asyncio.Event()
    stopping.set()
    logger = logging.getLogger("worker.example_a.report_item_count")
    with caplog.at_level(logging.INFO, logger="worker.example_a.report_item_count"):
        await asyncio.wait_for(report_item_count(LoopContext("example_a", "report_item_count", stopping, logger)), 2)
    assert "当前条目数" in caplog.text
