"""火山引擎 TOS 对象存储封装。"""

from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from pydantic import BaseModel, Field
from tos import TosClientV2
from tos.models2 import ACLType

from platforms.config import get_settings
from platforms.storage.object_storage import ObjectStorage


class TosUploadRecord(BaseModel):
    """一次上传操作的存档记录（入数据库/JSON 前用 .model_dump() / .model_dump_json()）。"""

    bucket: str
    key: str
    # 公开对象的访问地址；acl 为 private 时为 None
    url: str | None = None
    # 本次上传实际生效的 ACL
    acl: str = "private"
    # 对象大小（字节）；无法获知时为 None
    size: int | None = None
    # 内容校验（完整性核对）
    etag: str | None = None
    hash_crc64_ecma: int | None = None
    # bucket 开启版本控制时才有值
    version_id: str | None = None
    # 服务端响应信息（排查问题用）
    status_code: int | None = None
    request_id: str | None = None
    # 上传时间（本地时间）
    uploaded_at: datetime = Field(default_factory=datetime.now)


def _content_size(data: bytes | bytearray | BinaryIO) -> int | None:
    """尽力获取待上传内容的字节数，取不到返回 None。"""
    if isinstance(data, (bytes, bytearray)):
        return len(data)
    if hasattr(data, "seek") and hasattr(data, "tell"):
        try:
            pos = data.tell()
            data.seek(0, 2)  # 移到末尾
            size = data.tell()
            data.seek(pos)  # 恢复原位置
            return size
        except (OSError, ValueError):
            return None
    return None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


class TosStorage(ObjectStorage):
    """提供对象上传、下载、删除和存在性检查。"""

    def __init__(self, bucket: str | None = None, client: TosClientV2 | None = None):
        settings = get_settings()
        self._settings = settings
        self.bucket = bucket or settings.tos_bucket_name
        if not self.bucket:
            raise ValueError("TOS bucket 未配置，请设置 TOS_BUCKET_NAME 或传入 bucket")

        if client is None:
            missing = [
                name
                for name, value in (
                    ("TOS_ENDPOINT", settings.tos_endpoint),
                    ("TOS_ACCESS_KEY_ID", settings.tos_access_key_id),
                    ("TOS_SECRET_ACCESS_KEY", settings.tos_secret_access_key),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"TOS 配置缺失: {', '.join(missing)}")
            client = TosClientV2(
                ak=settings.tos_access_key_id,
                sk=settings.tos_secret_access_key,
                endpoint=settings.tos_endpoint,
                region=settings.tos_region,
            )
        self.client = client

    def _resolve_acl(self, acl: str | None) -> str:
        """解析上传 ACL：显式传参优先，否则用配置默认值。"""
        if acl is not None:
            return acl
        configured = getattr(self._settings, "tos_default_acl", None)
        return configured if isinstance(configured, str) and configured else "private"

    def _public_url(self, key: str) -> str:
        """拼公开访问地址：https://<bucket>.<endpoint>/<key>。"""
        host = self._settings.tos_endpoint
        host = host.split("://", 1)[-1].rstrip("/")
        return f"https://{self.bucket}.{host}/{quote(key, safe='/')}"

    def _to_record(
        self, key: str, acl: str, size: int | None, response: object
    ) -> TosUploadRecord:
        """把 SDK 原生返回转成标准存档记录（对 Mock 返回也兼容）。"""
        return TosUploadRecord(
            bucket=self.bucket,
            key=key,
            url=self._public_url(key) if acl != "private" else None,
            acl=acl,
            size=size,
            etag=_str_or_none(getattr(response, "etag", None)),
            hash_crc64_ecma=_int_or_none(getattr(response, "hash_crc64_ecma", None)),
            version_id=_str_or_none(getattr(response, "version_id", None)),
            status_code=_int_or_none(getattr(response, "status_code", None)),
            request_id=_str_or_none(getattr(response, "request_id", None)),
        )

    def upload(self, key: str, data: bytes | bytearray | BinaryIO, acl: str | None = None) -> TosUploadRecord:
        """上传 bytes 或二进制文件对象，返回 TosUploadRecord（用于存档）。

        acl 可选：private / public-read / public-read-write；缺省时用配置
        TOS_DEFAULT_ACL（默认 private）。
        """
        kwargs = {"content": data}
        acl = self._resolve_acl(acl)
        if acl != "private":
            kwargs["acl"] = ACLType(acl)
        size = _content_size(data)
        response = self.client.put_object(self.bucket, key, **kwargs)
        return self._to_record(key, acl, size, response)

    def upload_file(self, key: str, file_path: str | Path, acl: str | None = None) -> TosUploadRecord:
        """上传本地文件，返回 TosUploadRecord（用于存档）。"""
        with Path(file_path).open("rb") as file:
            return self.upload(key, file, acl=acl)

    def download_file(self, key: str) -> bytes:
        """下载对象并返回其完整内容。"""
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()

    def delete_file(self, key: str) -> None:
        """删除对象。"""
        self.client.delete_object(self.bucket, key)

    def exists(self, key: str) -> bool:
        """检查对象是否存在；TOS 对象不存在时 SDK 会抛出 TosServerError。"""
        from tos.exceptions import TosServerError

        try:
            self.client.head_object(self.bucket, key)
            return True
        except TosServerError as error:
            if getattr(error, "status_code", None) == 404:
                return False
            raise
