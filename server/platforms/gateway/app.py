"""应用装配：加载模块 → 注册事件订阅 → 挂载路由 → 启动生命周期钩子。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platforms import registry
from platforms.auth.admin_api import router as admin_router
from platforms.auth.api import router as auth_router
from platforms.auth.principal import (
    current_principal,
    principal_dependency,
    session_provider,
)
from platforms.config import Settings, get_settings
from platforms.contract import ModuleSpec
from platforms.gateway.api import router as platform_router
from platforms.gateway.errors import register_error_handlers
from platforms.gateway.loader import load_modules
from platforms.gateway.middleware import request_context
from platforms.lifecycle import module_lifecycle, subscribe_events


def _lifespan(modules: list[ModuleSpec]):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with module_lifecycle(modules):
            yield

    return lifespan


def create_app(settings: Settings | None = None, package: str = "modules") -> FastAPI:
    settings = settings or get_settings()
    modules = load_modules(settings.enabled_modules, package)
    registry.register(modules)

    if settings.auth_mode == "feishu":
        missing = [
            name
            for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_REDIRECT_URI")
            if not getattr(settings, name.lower())
        ]
        if missing:
            raise RuntimeError(f"AUTH_MODE=feishu 但缺少配置：{'、'.join(missing)}")
        auth_provider = session_provider
    else:
        auth_provider = None

    subscribe_events(modules)

    app = FastAPI(title="lancha-ai-studio", lifespan=_lifespan(modules))
    app.dependency_overrides[current_principal] = principal_dependency(auth_provider)

    # 路由里的 Depends(get_settings) 拿的是 lru_cache 的全局实例，
    # 不接管的话 create_app(settings) 传进来的配置对请求处理完全不生效。
    app.dependency_overrides[get_settings] = lambda: settings

    # add_middleware 后添加的在外层：CORS 放最外层，错误响应也能带上跨域头
    app.middleware("http")(request_context)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    register_error_handlers(app)

    @app.get("/health", tags=["platform"])
    async def health():
        return {"status": "ok", "modules": [spec.name for spec in modules]}

    app.include_router(platform_router, prefix="/api", tags=["platform"])
    app.include_router(auth_router, prefix="/api/auth", tags=["platform"])
    app.include_router(admin_router, prefix="/api/admin", tags=["platform"])
    for spec in modules:
        if spec.router is not None:
            app.include_router(spec.router, prefix=f"/api/{spec.name}", tags=[spec.name])

    return app
