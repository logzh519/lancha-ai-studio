"""统一启动入口：在 server 目录执行 python main.py。"""

import logging
import sys

import uvicorn

from platforms.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    uvicorn.run(
        "platforms.gateway.app:create_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        # psycopg 异步不支持 Windows 默认的 ProactorEventLoop，统一使用 SelectorEventLoop
        loop="asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto",
    )
