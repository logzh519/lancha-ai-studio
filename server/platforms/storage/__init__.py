from platforms.storage.factory import get_storage
from platforms.storage.object_storage import ObjectStorage
from platforms.storage.obs_storage import ObsError, ObsStorage, ObsUploadRecord
from platforms.storage.tos_storage import TosStorage, TosUploadRecord

__all__ = [
    "ObjectStorage",
    "ObsError",
    "ObsStorage",
    "ObsUploadRecord",
    "TosStorage",
    "TosUploadRecord",
    "get_storage",
]
