"""
Structured request logging middleware for Ada's FastAPI application.

Each HTTP request gets:
  - A unique request_id (UUID4, or taken from the incoming X-Request-ID header)
  - Timing via monotonic clock (duration_ms)
  - A structured access log entry at the end of every request (if access_log=True)
  - structlog contextvars bound for the lifetime of the request so any log
    statement emitted by route handlers and agents carries request_id
    automatically

The middleware is implemented as raw ASGI (not BaseHTTPMiddleware) to avoid
the double-wrapped async generator issues that BaseHTTPMiddleware has with
streaming responses.

The response always includes an X-Request-ID header so clients can correlate
logs to their own trace context.

@decision DEC-OBS-001
@title Correlation IDs via structlog contextvars
@status accepted
@rationale contextvars are async-safe (unlike thread-locals), ensuring
    request IDs don't leak between concurrent requests in uvicorn.
    Raw ASGI middleware receives the scope/receive/send directly and passes
    them through without re-wrapping. This is the pattern recommended by the
    Starlette maintainers for any middleware that needs to observe but not
    buffer the response.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ada.core.config import LoggingConfig


log = structlog.get_logger(__name__)


class StructlogRequestMiddleware:
    """
    ASGI middleware that assigns a request_id and emits a structured access log
    entry for every HTTP request.

    Skips the access-log emission for WebSocket connections (scope type
    "websocket") because those are long-lived and the connect/disconnect
    events are more meaningful than duration of the whole socket.

    Args:
        app: The next ASGI application in the middleware stack.
        logging_config: Ada's LoggingConfig section (for request_id_header and
            access_log flags).
    """

    def __init__(self, app: Callable, logging_config: "LoggingConfig") -> None:
        self.app = app
        self._rid_header = logging_config.request_id_header.lower()
        self._access_log = logging_config.access_log
        self._slow_threshold_ms = logging_config.slow_request_threshold_ms

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        # Only instrument HTTP — pass WebSocket/lifespan straight through
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # --- Extract or generate request_id ---
        request_id = _extract_request_id(scope, self._rid_header)

        # --- Bind to structlog context for this async task ---
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        if scope["type"] == "websocket":
            # For WebSockets just pass through — the request_id is bound above
            await self.app(scope, receive, send)
            structlog.contextvars.clear_contextvars()
            return

        # --- HTTP: wrap send to capture status_code and inject response header ---
        status_code: list[int] = [0]
        headers_sent: list[bool] = [False]

        rid_header_value = request_id.encode()
        rid_header_name = self._rid_header.encode()

        async def send_with_request_id(message: dict) -> None:
            if message["type"] == "http.response.start" and not headers_sent[0]:
                headers_sent[0] = True
                status_code[0] = message.get("status", 0)

                # Append X-Request-ID to response headers
                existing: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                existing.append((rid_header_name, rid_header_value))
                message = {**message, "headers": existing}

            await send(message)

        # --- Timing ---
        start = time.monotonic()
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            if self._access_log:
                method, path = _extract_method_path(scope)
                log_method = log.warning if duration_ms > self._slow_threshold_ms else log.info
                log_method(
                    "request",
                    method=method,
                    path=path,
                    status=status_code[0],
                    duration_ms=duration_ms,
                    request_id=request_id,
                )
            structlog.contextvars.clear_contextvars()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_request_id(scope: dict, header_name: str) -> str:
    """
    Read the request_id from incoming headers or generate a new UUID4.

    Args:
        scope: ASGI connection scope.
        header_name: Lower-cased header name to look for (e.g. "x-request-id").

    Returns:
        A request_id string — either from the incoming header or a fresh UUID4.
    """
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    name_bytes = header_name.encode()
    for k, v in headers:
        if k.lower() == name_bytes:
            rid = v.decode(errors="replace").strip()
            if rid:
                return rid
    return str(uuid.uuid4())


def _extract_method_path(scope: dict) -> tuple[str, str]:
    """
    Extract HTTP method and path from the ASGI scope.

    Args:
        scope: ASGI connection scope.

    Returns:
        (method, path) tuple — both strings.
    """
    method: str = scope.get("method", "UNKNOWN")
    path: str = scope.get("path", "/")
    query: bytes = scope.get("query_string", b"")
    if query:
        path = f"{path}?{query.decode(errors='replace')}"
    return method, path
