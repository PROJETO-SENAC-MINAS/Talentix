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
from app.core.session import csrf_valido


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Limite por processo/cliente; o bloqueio de login também é persistido no banco."""
    def __init__(self, app):
        super().__init__(app)
        self._hits = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/saude", "/"} or request.method == "OPTIONS":
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        partes = [parte for parte in request.url.path.split("/") if parte]
        eh_auth = bool(partes and partes[0] == "auth")
        limite = settings.RATE_LIMIT_AUTH_REQUESTS if eh_auth else settings.RATE_LIMIT_REQUESTS
        if eh_auth:
            # Autenticação precisa de limite mais rígido, mas não deve colocar
            # cadastro, login, recuperação e 2FA no mesmo balde.
            grupo = "auth:" + (partes[1] if len(partes) > 1 else "root")
        else:
            # Agrupa por domínio de API para impedir evasão por IDs diferentes.
            grupo = partes[0] if partes else "root"
        key = f"{client}:{grupo}"
        now = time.monotonic()
        async with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] >= settings.RATE_LIMIT_WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= limite:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Muitas requisições. Tente novamente em instantes."},
                    headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
                )
            bucket.append(now)
        return await call_next(request)


class SecurityMiddleware(BaseHTTPMiddleware):
    """CSRF, limite de payload e cabeçalhos defensivos para toda a API."""
    _MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        tamanho = request.headers.get("content-length")
        if tamanho:
            try:
                if int(tamanho) > settings.MAX_REQUEST_SIZE_MB * 1024 * 1024:
                    return JSONResponse(status_code=413, content={"detail": "Requisição grande demais."})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Content-Length inválido."})

        if (
            request.method in self._MUTATING
            and request.cookies.get(settings.SESSION_COOKIE_NAME)
            and not csrf_valido(request)
        ):
            return JSONResponse(status_code=403, content={"detail": "Token CSRF ausente ou inválido."})

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/auth/"):
            response.headers["Cache-Control"] = "no-store"
        if settings.SESSION_COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
