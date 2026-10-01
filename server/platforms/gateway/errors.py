"""统一错误响应：{"code": HTTP 状态码, "message": 说明, "request_id": ..., "details": 可选}。"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger("platform.gateway.error")


def _error(request: Request, status: int, message: str, details=None, headers=None) -> JSONResponse:
    body = {"code": status, "message": message, "request_id": getattr(request.state, "request_id", None)}
    if details is not None:
        body["details"] = jsonable_encoder(details)
    return JSONResponse(body, status_code=status, headers=headers)


async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return _error(request, exc.status_code, str(exc.detail), headers=exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(request, 422, "请求参数校验失败", details=exc.errors())


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理的异常 %s %s", request.method, request.url.path)
    return _error(request, 500, "服务器内部错误")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
