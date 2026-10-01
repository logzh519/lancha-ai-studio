"""平台配置，优先级：环境变量 > .env 文件 > 默认值；各模块自己的配置写在 modules/<模块名>/config.py。"""

from functools import lru_cache
from typing import Annotated, Literal

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

    # 认证方式：dev_header 用 X-User-Id 请求头（仅限本地开发），feishu 走飞书扫码登录。
    # 做成显式开关而不是「配了 app_id 就自动启用」：漏配时静默退回无认证，在生产上没人会发现。
    # 用 Literal 而非 str：拼写错误若仍接受任意字符串，服务会启动但实际走 dev_header（信任 X-User-Id），等于无认证且无告警。
    auth_mode: Literal["dev_header", "feishu"] = "dev_header"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    # 飞书会把浏览器直接重定向到这个地址，开发期必须填前端地址（Vite 代理转发），
    # 填后端地址会让 cookie 落在后端域下，前端带不过去。
    feishu_redirect_uri: str = ""
    feishu_scope: str = "auth:user.id:read contact:user.employee:readonly"
    session_ttl_days: int = 7
    cookie_secure: bool = False
    frontend_base_url: str = "http://localhost:5173"

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
