"""对象存储抽象基类。"""

from abc import ABC, abstractmethod
from pathlib import Path


class ObjectStorage(ABC):
    """对象存储通用接口，具体存储服务继承并实现。"""

    @abstractmethod
    def upload_file(self, key: str, file_path: str | Path) -> object:
        """上传本地文件到 key，返回具体实现的上传记录。"""

    @abstractmethod
    def download_file(self, key: str) -> bytes:
        """下载对象并返回其完整内容。"""

    @abstractmethod
    def delete_file(self, key: str) -> None:
        """删除对象。"""
