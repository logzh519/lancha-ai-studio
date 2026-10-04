"""模块配置：环境变量前缀为 <模块名大写>_，避免和平台及其他模块的配置项撞名。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class TiktokSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TIKTOK_", extra="ignore")

    page_size: int = 20


@lru_cache
def get_settings() -> TiktokSettings:
    return TiktokSettings()
