"""
Unit tests for ada.api.middleware.rate_limit.RateLimitMiddleware.

Covers:
- Requests below the limit return 200
- Exceeding the limit returns 429 with a Retry-After header
- Auth-prefix paths enforce the tighter auth_requests_per_minute limit
  while non-auth paths use api_requests_per_minute
- When enabled=False the middleware is a transparent pass-through

Uses httpx.ASGITransport (no server) with a minimal FastAPI app — same
pattern as test_logging_middleware.py.  All tests create a fresh middleware
instance so counters don't leak between tests.

@decision DEC-SEC-001
@title In-memory sliding window rate limiter — test coverage
@status accepted
@rationale Validates per-IP counter logic, path-based limit selection, 429
    short-circuit response (including Retry-After header), and the enabled=False
    bypass path.  No mocks of internal modules — tests operate on the real
    implementation via real ASGI dispatch.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from ada.api.middleware.rate_limit import RateLimitMiddleware
from ada.core.config import RateLimitConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(cfg: RateLimitConfig) -> FastAPI:
    """Minimal FastAPI app wrapped with RateLimitMiddleware."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rate_limit_config=cfg)

    @app.get("/api/users")
    async def api_users() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.post("/api/auth/login")
    async def auth_login() -> PlainTextResponse:
        return PlainTextResponse("token")

    return app


def _cfg(**overrides) -> RateLimitConfig:
    return RateLimitConfig(**overrides)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_requests_under_limit_return_200():
    """Multiple requests under the per-minute cap all succeed."""
    cfg = _cfg(enabled=True, api_requests_per_minute=5)
    app = _make_app(cfg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(5):
            response = await client.get("/api/users")
            assert response.status_code == 200, (
                f"Expected 200 but got {response.status_code}"
            )


@pytest.mark.asyncio
async def test_exceeding_limit_returns_429_with_retry_after():
    """The (n+1)th request exceeding the cap returns 429 with Retry-After."""
    cfg = _cfg(enabled=True, api_requests_per_minute=3)
    app = _make_app(cfg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for i in range(3):
            r = await client.get("/api/users")
            assert r.status_code == 200, f"Request {i+1} should be 200"

        # 4th request should be rate-limited
        over_limit = await client.get("/api/users")
        assert over_limit.status_code == 429
        assert "retry-after" in over_limit.headers
        assert over_limit.headers["retry-after"] == "60"
        body = over_limit.json()
        assert body["detail"] == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_auth_routes_have_tighter_limit_than_api_routes():
    """
    Auth paths enforce auth_requests_per_minute (tight) while non-auth paths
    enforce api_requests_per_minute (loose).  With auth=2 and api=100 the
    auth path is blocked on the 3rd request while the api path is still open.
    """
    cfg = _cfg(
        enabled=True,
        auth_requests_per_minute=2,
        api_requests_per_minute=100,
    )
    app = _make_app(cfg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Exhaust the auth limit
        for _ in range(2):
            r = await client.post("/api/auth/login")
            assert r.status_code == 200

        # 3rd auth request → 429
        r = await client.post("/api/auth/login")
        assert r.status_code == 429, "Auth route should be rate-limited"

        # API route is still under its own (much higher) limit
        r = await client.get("/api/users")
        assert r.status_code == 200, "Non-auth route should still be open"


@pytest.mark.asyncio
async def test_rate_limiter_bypassed_when_disabled():
    """When enabled=False, all requests pass through regardless of volume."""
    cfg = _cfg(enabled=False, api_requests_per_minute=1)
    app = _make_app(cfg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for i in range(10):
            r = await client.get("/api/users")
            assert r.status_code == 200, (
                f"Request {i+1} should be 200 when limiter disabled"
            )
