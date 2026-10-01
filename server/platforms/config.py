"""平台配置，优先级：环境变量 > .env 文件 > 默认值；各模块自己的配置写在 modules/<模块名>/config.py。"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 网关监听地址与端口（对外唯一服务端口）
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"

    # 允许跨域的前端地址，逗号分隔；为空则不开启跨域
    cors_origins: Annotated[list[str], NoDecode] = []

    # 启用的业务模块（modules/ 下的目录名），逗号分隔；为空则加载全部模块
    enabled_modules: Annotated[list[str], NoDecode] = []

    # PostgreSQL：全平台共用一个库，按 schema 隔离（见 platforms/db.py）
    # 用 127.0.0.1 而非 localhost：Windows 上 localhost 优先解析为 ::1，Docker 端口转发不通会卡住
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str = "lancha"
    postgres_password: str = ""
    postgres_db: str = "lancha_ai_studio"
    postgres_pool_size: int = 5
    postgres_max_overflow: int = 10

    @field_validator("cors_origins", "enabled_modules", mode="before")
    @classmethod
    def _split_csv(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


# 单例缓存
@lru_cache
def get_settings() -> Settings:
    return Settings()
