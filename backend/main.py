"""统一启动入口：在 backend 目录执行 python main.py。"""

import logging

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
    )
