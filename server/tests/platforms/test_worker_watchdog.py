"""看门狗：事件循环被阻塞超过阈值时触发，正常运行时不触发。"""

import asyncio
import threading
import time

from platforms.worker.watchdog import Watchdog


async def test_fires_when_event_loop_is_blocked():
    fired = threading.Event()
    watchdog = Watchdog(0.2, on_timeout=lambda lag, timeout: fired.set())
    watchdog.start()
    try:
        time.sleep(0.6)  # noqa: ASYNC251
        assert fired.wait(1)
    finally:
        await watchdog.stop()


async def test_does_not_fire_when_event_loop_is_healthy():
    fired = threading.Event()
    watchdog = Watchdog(0.2, on_timeout=lambda lag, timeout: fired.set())
    watchdog.start()
    try:
        await asyncio.sleep(0.6)
        assert not fired.is_set()
    finally:
        await watchdog.stop()
