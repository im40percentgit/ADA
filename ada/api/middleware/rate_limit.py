"""
In-process sliding window rate limiting middleware for Ada.

Uses a per-IP deque of monotonic timestamps. On every request the deque is
pruned of entries older than 60 s, then the length is compared against the
configured limit for that path prefix. When the limit is exceeded the
middleware short-circuits with a 429 and a Retry-After header; otherwise the
request passes to the next ASGI callable unchanged.

@decision DEC-SEC-001
@title In-memory sliding window rate limiter (no Redis)
@status accepted
@rationale Single-process deployment (SQLite write-contention). Revisit for
    multi-instance deployments. Counters live in process memory and reset on
    restart — this is intentional for Phase 6 scope. A Redis-backed alternative
    would be introduced only if horizontal scaling is needed.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ada.core.config import RateLimitConfig


_WINDOW_SECONDS = 60.0


class RateLimitMiddleware:
    """
    Raw ASGI sliding window rate limiter.

    Limits are applied per client IP:
      - Paths starting with ``/api/auth`` → ``auth_requests_per_minute``
      - All other paths                  → ``api_requests_per_minute``

    Non-HTTP scopes (websocket, lifespan) pass through without incrementing
    any counter because they are long-lived connections, not per-request load.
    WebSocket connection-level limits (ws_connections_per_ip) are tracked
    separately but enforcement happens at the WS upgrade boundary, not here.

    Args:
        app: Next ASGI callable.
        rate_limit_config: Ada's RateLimitConfig section.
    """

    def __init__(self, app: Callable, rate_limit_config: "RateLimitConfig") -> None:
        self.app = app
        self._cfg = rate_limit_config
        # ip -> deque[float] of monotonic timestamps within the window
        self._counters: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        # Only rate-limit HTTP — pass everything else straight through
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Bypass when disabled (e.g. tests, local dev)
        if not self._cfg.enabled:
            await self.app(scope, receive, send)
            return

        client_ip = _extract_ip(scope)
        path: str = scope.get("path", "/")
        limit = self._limit_for_path(path)

        now = time.monotonic()
        bucket = self._counters[client_ip]

        # Prune stale entries (older than the 60-second window)
        cutoff = now - _WINDOW_SECONDS
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            await _send_429(send)
            return

        bucket.append(now)
        await self.app(scope, receive, send)

    def _limit_for_path(self, path: str) -> int:
        """Return the per-minute limit appropriate for *path*."""
        if path.startswith("/api/auth"):
            return self._cfg.auth_requests_per_minute
        return self._cfg.api_requests_per_minute


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_ip(scope: dict) -> str:
    """
    Extract the client IP from the ASGI scope.

    Returns ``"unknown"`` when the scope carries no client tuple (e.g. tests
    that don't populate it).
    """
    client = scope.get("client")
    if client and isinstance(client, (list, tuple)) and len(client) >= 1:
        return str(client[0])
    return "unknown"


async def _send_429(send: Callable) -> None:
    """Send a minimal 429 JSON response with Retry-After: 60."""
    body = json.dumps({"detail": "Rate limit exceeded"}).encode()
    await send({
        "type": "http.response.start",
        "status": 429,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"retry-after", b"60"),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
        "more_body": False,
    })
