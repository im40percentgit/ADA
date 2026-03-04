"""
Security headers and body-size enforcement middleware for Ada.

Every HTTP response receives a fixed set of security headers that protect
against common browser-level attacks (MIME sniffing, clickjacking, referrer
leakage). Requests with a Content-Length header that exceeds the configured
body size limit are rejected before they reach any route handler.

@decision DEC-SEC-002
@title Security headers + body size at middleware level
@status accepted
@rationale Defense-in-depth. Path-differentiated body limits allow media
    routes to accept up to 10 MB while keeping the general API limit at 1 MB.
    Injecting headers once in middleware is DRYer than per-route decoration and
    ensures every future route gets the headers automatically.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ada.core.config import SecurityConfig


# Headers injected on every HTTP response.
_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(self), microphone=(self)"),
]

# Path fragments that qualify for the larger media body-size limit.
_MEDIA_PATH_FRAGMENTS = ("/media", "/audio", "/video", "/sensor")


class SecurityHeadersMiddleware:
    """
    Raw ASGI middleware: inject security headers and enforce body size limits.

    Body size is determined by the ``Content-Length`` request header.
    Requests without a Content-Length are allowed through (streaming / chunked
    transfer — the application layer is responsible for those).

    Args:
        app: Next ASGI callable.
        security_config: Ada's SecurityConfig section.
    """

    def __init__(self, app: Callable, security_config: "SecurityConfig") -> None:
        self.app = app
        self._cfg = security_config

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        # Only act on HTTP — pass everything else straight through
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # --- Body size enforcement ---
        path: str = scope.get("path", "/")
        limit = self._body_limit_for_path(path)
        content_length = _extract_content_length(scope)

        if content_length is not None and content_length > limit:
            await _send_413(send)
            return

        # --- Wrap send to inject security headers into the response ---
        async def send_with_security_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                existing: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                existing.extend(_SECURITY_HEADERS)
                message = {**message, "headers": existing}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)

    def _body_limit_for_path(self, path: str) -> int:
        """Return the body-size limit appropriate for *path*."""
        for fragment in _MEDIA_PATH_FRAGMENTS:
            if fragment in path:
                return self._cfg.max_media_body_size_bytes
        return self._cfg.max_body_size_bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_content_length(scope: dict) -> int | None:
    """
    Parse the Content-Length header from the ASGI request scope.

    Returns the integer value if present and valid, otherwise ``None``.
    """
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for name, value in headers:
        if name.lower() == b"content-length":
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
    return None


async def _send_413(send: Callable) -> None:
    """Send a minimal 413 JSON response."""
    body = json.dumps({"detail": "Request body too large"}).encode()
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
        "more_body": False,
    })
