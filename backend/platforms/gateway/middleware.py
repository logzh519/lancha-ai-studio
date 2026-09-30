"""统一请求拦截：为每个请求分配 request_id，并记录访问日志。"""

import logging
import time
import uuid

from fastapi import Request

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("platform.gateway.access")


async def request_context(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    logger.info(
        "%s %s %s %.1fms request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
        request_id,
    )
    return response
