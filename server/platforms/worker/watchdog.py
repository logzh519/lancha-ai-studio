"""事件循环看门狗：循环卡死时打印所有线程堆栈并退出进程，交给 compose / systemd 重启。

卡死的事件循环里，asyncio 的超时也不会触发，只能由独立线程从外部判定。
进程退出后数据库连接随之关闭，持有的单例锁会被释放，其他副本得以接管。
"""

import asyncio
import faulthandler
import logging
import os
import sys
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("platform.worker")

# 卡死的主线程可能持有日志锁或 stderr 管道已满，写日志、打堆栈都可能阻塞，到期强制退出
_EXIT_FALLBACK_SECONDS = 5.0


def _exit_process(lag: float, timeout: float) -> None:
    fallback = threading.Timer(_EXIT_FALLBACK_SECONDS, os._exit, (1,))
    fallback.daemon = True
    fallback.start()
    logger.critical("事件循环已阻塞 %.1f 秒，超过看门狗阈值 %.1f 秒，进程退出", lag, timeout)
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
    os._exit(1)


class Watchdog:
    def __init__(self, timeout: float, on_timeout: Callable[[float, float], None] = _exit_process):
        self._timeout = timeout
        self._on_timeout = on_timeout
        self._interval = min(1.0, timeout / 4)
        self._last_tick = time.monotonic()
        self._stopped = threading.Event()
        self._tick_task: asyncio.Task | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """在运行中的事件循环内调用。"""
        self._last_tick = time.monotonic()
        self._tick_task = asyncio.get_running_loop().create_task(self._tick())
        self._thread = threading.Thread(target=self._watch, name="worker-watchdog", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._stopped.set()
        if self._tick_task is not None:
            self._tick_task.cancel()
            await asyncio.gather(self._tick_task, return_exceptions=True)
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join)

    async def _tick(self) -> None:
        while True:
            self._last_tick = time.monotonic()
            await asyncio.sleep(self._interval)

    def _watch(self) -> None:
        while not self._stopped.wait(self._interval):
            lag = time.monotonic() - self._last_tick
            if lag > self._timeout:
                self._on_timeout(lag, self._timeout)
                return
