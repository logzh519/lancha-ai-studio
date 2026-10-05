"""获取具体的对象存储实例。"""

from functools import lru_cache

from platforms.config import get_settings
from platforms.storage.object_storage import ObjectStorage
from platforms.storage.obs_storage import ObsStorage
from platforms.storage.tos_storage import TosStorage

_PROVIDERS: dict[str, type[ObjectStorage]] = {cls.type: cls for cls in (TosStorage, ObsStorage)}


def get_storage(provider: str | None = None) -> ObjectStorage:
    """返回进程内共享的对象存储实例。

    provider 可选：tos（火山引擎 TOS）/ obs（华为云 OBS）；缺省时用配置 STORAGE_PROVIDER，
    配置也为空时用 tos。
    """
    provider = (provider or get_settings().storage_provider).strip().lower() or "tos"
    return _create_storage(provider)


@lru_cache
def _create_storage(provider: str) -> ObjectStorage:
    storage_cls = _PROVIDERS.get(provider)
    if storage_cls is None:
        raise ValueError(f"不支持的对象存储: {provider}，可选: {', '.join(_PROVIDERS)}")
    return storage_cls()
