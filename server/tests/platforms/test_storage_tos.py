"""TOS 存储封装：SDK 客户端全部 mock，不打真实网络。"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tos.exceptions import TosServerError

from platforms.storage import tos_storage
from platforms.storage.tos_storage import TosStorage


class FakeResponse(BytesIO):
    pass


def make_storage(monkeypatch, client=None, bucket="test-bucket"):
    settings = Mock(
        tos_bucket_name=bucket,
        tos_endpoint="https://tos.example.com",
        tos_access_key_id="test-ak",
        tos_secret_access_key="test-sk",
    )
    monkeypatch.setattr(tos_storage, "get_settings", lambda: settings)
    return TosStorage(client=client or Mock())


def test_upload_file_uses_file_contents(monkeypatch, tmp_path):
    client = Mock()
    uploaded = {}

    def capture_upload(bucket, key, content):
        uploaded["bucket"] = bucket
        uploaded["key"] = key
        uploaded["content"] = content.read()

    client.put_object.side_effect = capture_upload
    storage = make_storage(monkeypatch, client)
    test_file = tmp_path / "helloworld.txt"
    test_file.write_bytes(b"hello world")

    storage.upload_file("samples/helloworld.txt", test_file)

    assert uploaded == {
        "bucket": "test-bucket",
        "key": "samples/helloworld.txt",
        "content": test_file.read_bytes(),
    }


def test_upload_bytes(monkeypatch):
    client = Mock()
    storage = make_storage(monkeypatch, client)

    storage.upload("hello.txt", b"hello")

    client.put_object.assert_called_once_with("test-bucket", "hello.txt", content=b"hello")


def test_download_returns_bytes_and_closes_response(monkeypatch):
    client = Mock()
    response = FakeResponse(b"hello")
    client.get_object.return_value = response
    storage = make_storage(monkeypatch, client)

    assert storage.download_file("hello.txt") == b"hello"
    assert response.closed
    client.get_object.assert_called_once_with("test-bucket", "hello.txt")


def test_delete(monkeypatch):
    client = Mock()
    storage = make_storage(monkeypatch, client)

    storage.delete_file("hello.txt")

    client.delete_object.assert_called_once_with("test-bucket", "hello.txt")


def test_exists_returns_false_for_missing_object(monkeypatch):
    client = Mock()
    error = TosServerError(
        SimpleNamespace(request_id="test", headers={}, status=404),
        "not found",
        "NoSuchKey",
        "",
        "missing.txt",
    )
    client.head_object.side_effect = error
    storage = make_storage(monkeypatch, client)

    assert storage.exists("missing.txt") is False


def test_upload_returns_record(monkeypatch):
    client = Mock()
    client.put_object.return_value = SimpleNamespace(
        etag="abc123",
        hash_crc64_ecma=987654321,
        version_id=None,
        status_code=200,
        request_id="req-001",
    )
    storage = make_storage(monkeypatch, client)

    record = storage.upload("hello.txt", b"hello", acl="public-read")

    assert record.bucket == "test-bucket"
    assert record.key == "hello.txt"
    assert record.acl == "public-read"
    assert record.size == 5
    assert record.url == "https://test-bucket.tos.example.com/hello.txt"
    assert record.etag == "abc123"
    assert record.hash_crc64_ecma == 987654321
    assert record.status_code == 200
    assert record.request_id == "req-001"
    # 私有对象不生成公开 URL
    private = storage.upload("secret.txt", b"x", acl="private")
    assert private.url is None


def test_bucket_is_required(monkeypatch):
    settings = Mock(
        tos_bucket_name="",
        tos_endpoint="",
        tos_access_key_id="",
        tos_secret_access_key="",
    )
    monkeypatch.setattr(tos_storage, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="TOS_BUCKET_NAME"):
        TosStorage()
