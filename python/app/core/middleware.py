"""Middlewares operacionais compartilhados."""
from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("talentix.http")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


from collections import defaultdict, deque
import asyncio

from starlette.responses import JSONResponse
from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Limite por processo/cliente; o bloqueio de login também é persistido no banco."""
    def __init__(self, app):
        super().__init__(app)
        self._hits = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/saude", "/"} or request.method == "OPTIONS":
            return await call_next(request)
        forwarded = request.headers.get("x-forwarded-for", "")
        client = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
        key = f"{client}:{request.url.path.split('/')[1] if '/' in request.url.path else request.url.path}"
        now = time.monotonic()
        async with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] >= settings.RATE_LIMIT_WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= settings.RATE_LIMIT_REQUESTS:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Muitas requisições. Tente novamente em instantes."},
                    headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
                )
            bucket.append(now)
        return await call_next(request)
