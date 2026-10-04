"""统一启动入口：在 server 目录执行。

python main.py                                   启动 API 网关（等同 python main.py api）
python main.py worker <模块>[,<模块>]            运行这些模块声明的全部后台循环
python main.py worker <模块> --loops a,b         只运行该模块内的部分循环
"""

import argparse
import asyncio
import logging
import sys

import uvicorn

from platforms.config import Settings, get_settings
from platforms.gateway.loader import ModuleLoadError
from platforms.worker.runner import WorkerConfigError, run_worker


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python main.py")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("api", help="启动 API 网关（默认）")
    worker = commands.add_parser("worker", help="运行模块声明的后台循环")
    worker.add_argument("modules", type=_csv, help="模块名，多个用逗号分隔")
    worker.add_argument("--loops", type=_csv, default=[], help="只运行模块内的这些循环，逗号分隔；仅限单个模块")
    return parser.parse_args(argv)


def _run_api(settings: Settings) -> None:
    uvicorn.run(
        "platforms.gateway.app:create_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        # psycopg 异步不支持 Windows 默认的 ProactorEventLoop，统一使用 SelectorEventLoop
        loop="asyncio:SelectorEventLoop" if sys.platform == "win32" else "auto",
    )


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    if args.command == "worker":
        try:
            asyncio.run(run_worker(settings, args.modules, args.loops))
        except (WorkerConfigError, ModuleLoadError) as exc:
            sys.exit(f"worker 启动失败：{exc}")
    else:
        _run_api(settings)
