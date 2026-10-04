"""部署前置步骤：依次迁移 platform 和已启用模块的 schema，再同步权限点。

用法：python scripts/migrate.py
分支顺序为 platform 在前，模块按依赖顺序在后；没有 migrations/versions 目录的模块跳过。
有迁移目录的模块必须在 alembic.ini 中配置同名分支，缺失时直接失败，避免漏迁移。
"""

import asyncio
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from platforms.config import get_settings  # noqa: E402
from platforms.db import PLATFORM_SCHEMA  # noqa: E402
from platforms.gateway.loader import load_modules  # noqa: E402
from sync_permissions import main as sync_permissions  # noqa: E402


def migration_branches() -> list[str]:
    modules = [spec.name for spec in load_modules(get_settings().enabled_modules)]
    with_migrations = [name for name in modules if (SERVER_DIR / "modules" / name / "migrations" / "versions").is_dir()]
    return [PLATFORM_SCHEMA, *with_migrations]


def upgrade(branch: str) -> None:
    config = Config(str(SERVER_DIR / "alembic.ini"), ini_section=branch)
    if not config.get_section(branch):
        raise SystemExit(f"模块 {branch} 有迁移目录，但 alembic.ini 中缺少 [{branch}] 配置段")
    print(f"迁移分支 {branch} -> head")
    command.upgrade(config, "head")


def main() -> None:
    for branch in migration_branches():
        upgrade(branch)
    # psycopg 异步不支持 Windows 默认的 ProactorEventLoop，统一使用 SelectorEventLoop
    asyncio.run(sync_permissions(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)


if __name__ == "__main__":
    main()
