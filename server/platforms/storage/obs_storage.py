"""华为云 OBS 对象存储封装。"""

from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from obs import ObsClient, PutObjectHeader
from pydantic import BaseModel, Field

from platforms.config import get_settings
from platforms.storage.object_storage import ObjectStorage


class ObsUploadRecord(BaseModel):
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
    crc64: str | None = None
    # bucket 开启版本控制时才有值
    version_id: str | None = None
    # 服务端响应信息（排查问题用）
    status_code: int | None = None
    request_id: str | None = None
    # 上传时间（本地时间）
    uploaded_at: datetime = Field(default_factory=datetime.now)


class ObsError(RuntimeError):
    """OBS 请求失败（SDK 不抛异常，而是返回 status >= 300 的响应）。"""

    def __init__(self, action: str, response: object):
        self.status_code = getattr(response, "status", None)
        self.error_code = getattr(response, "errorCode", None)
        self.request_id = getattr(response, "requestId", None)
        super().__init__(
            f"OBS {action} 失败: status={self.status_code}, code={self.error_code}, "
            f"message={getattr(response, 'errorMessage', None)}, request_id={self.request_id}"
        )


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


def _check(action: str, response: object) -> object:
    status = getattr(response, "status", None)
    if not isinstance(status, int) or status >= 300:
        raise ObsError(action, response)
    return response


class ObsStorage(ObjectStorage):
    """提供对象上传、下载、删除和存在性检查。"""

    type = "obs"

    def __init__(self, bucket: str | None = None, client: ObsClient | None = None):
        settings = get_settings()
        self._settings = settings
        self.bucket = bucket or settings.obs_bucket_name
        if not self.bucket:
            raise ValueError("OBS bucket 未配置，请设置 OBS_BUCKET_NAME 或传入 bucket")

        if client is None:
            missing = [
                name
                for name, value in (
                    ("OBS_ENDPOINT", settings.obs_endpoint),
                    ("OBS_ACCESS_KEY_ID", settings.obs_access_key_id),
                    ("OBS_SECRET_ACCESS_KEY", settings.obs_secret_access_key),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"OBS 配置缺失: {', '.join(missing)}")
            client = ObsClient(
                access_key_id=settings.obs_access_key_id,
                secret_access_key=settings.obs_secret_access_key,
                server=self._server(),
            )
        self.client = client

    def _server(self) -> str:
        """SDK 需要带协议的地址，缺省补 https://。"""
        endpoint = self._settings.obs_endpoint.rstrip("/")
        return endpoint if "://" in endpoint else f"https://{endpoint}"

    def _resolve_acl(self, acl: str | None) -> str:
        """解析上传 ACL：显式传参优先，否则用配置默认值。"""
        if acl is not None:
            return acl
        configured = getattr(self._settings, "obs_default_acl", None)
        return configured if isinstance(configured, str) and configured else "private"

    def _public_url(self, key: str) -> str:
        """拼公开访问地址：https://<bucket>.<endpoint>/<key>。"""
        host = self._settings.obs_endpoint.split("://", 1)[-1].rstrip("/")
        return f"https://{self.bucket}.{host}/{quote(key, safe='/')}"

    def _to_record(
        self, key: str, acl: str, size: int | None, response: object
    ) -> ObsUploadRecord:
        """把 SDK 原生返回转成标准存档记录（对 Mock 返回也兼容）。"""
        body = getattr(response, "body", None)
        return ObsUploadRecord(
            bucket=self.bucket,
            key=key,
            url=self._public_url(key) if acl != "private" else None,
            acl=acl,
            size=size,
            etag=_str_or_none(getattr(body, "etag", None)),
            crc64=_str_or_none(getattr(body, "crc64", None)),
            version_id=_str_or_none(getattr(body, "versionId", None)),
            status_code=_int_or_none(getattr(response, "status", None)),
            request_id=_str_or_none(getattr(response, "requestId", None)),
        )

    def upload(self, key: str, data: bytes | bytearray | BinaryIO, acl: str | None = None) -> ObsUploadRecord:
        """上传 bytes 或二进制文件对象，返回 ObsUploadRecord（用于存档）。

        acl 可选：private / public-read / public-read-write；缺省时用配置
        OBS_DEFAULT_ACL（默认 private）。
        """
        acl = self._resolve_acl(acl)
        headers = PutObjectHeader(acl=acl) if acl != "private" else None
        size = _content_size(data)
        # autoClose=False：文件对象由调用方管理生命周期
        response = self.client.putContent(
            self.bucket, key, content=bytes(data) if isinstance(data, bytearray) else data,
            headers=headers, autoClose=False,
        )
        _check("putContent", response)
        return self._to_record(key, acl, size, response)

    def upload_file(self, key: str, file_path: str | Path, acl: str | None = None) -> ObsUploadRecord:
        """上传本地文件，返回 ObsUploadRecord（用于存档）。"""
        with Path(file_path).open("rb") as file:
            return self.upload(key, file, acl=acl)

    def download_file(self, key: str) -> bytes:
        """下载对象并返回其完整内容。"""
        response = _check("getObject", self.client.getObject(self.bucket, key, loadStreamInMemory=True))
        return response.body.buffer

    def delete_file(self, key: str) -> None:
        """删除对象。"""
        _check("deleteObject", self.client.deleteObject(self.bucket, key))

    def exists(self, key: str) -> bool:
        """检查对象是否存在；OBS 对象不存在时返回 status 404。"""
        response = self.client.headObject(self.bucket, key)
        if getattr(response, "status", None) == 404:
            return False
        _check("headObject", response)
        return True
