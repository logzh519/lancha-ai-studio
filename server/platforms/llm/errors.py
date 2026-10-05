"""统一异常：两家 SDK 的错误都包装成 LLMError，消费方只处理一种异常。"""
from __future__ import annotations


class LLMError(Exception):
    def __init__(self, message: str, status_code: int | None = None,
                 error_type: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type


_TYPE_BY_STATUS = {401: "authentication_error", 429: "rate_limit_error"}


def wrap_error(e: Exception) -> LLMError:
    status = getattr(e, "status_code", None)
    if status is None:
        error_type = "connection_error"
    else:
        error_type = _TYPE_BY_STATUS.get(status, "api_error")
    return LLMError(str(e), status_code=status, error_type=error_type)
