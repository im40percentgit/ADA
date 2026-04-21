"""
Unit tests for ada.api.middleware.rate_limit.RateLimitMiddleware.

Covers:
- Requests below the limit return 200
- Exceeding the limit returns 429 with a Retry-After header
- Auth-prefix paths enforce the tighter auth_requests_per_minute limit
  while non-auth paths use api_requests_per_minute
- /api/auth/me is carved out of the auth bucket (DEC-SEC-003): hammering
  it beyond auth_requests_per_minute does NOT produce 429 — it counts
  against the (larger) api bucket instead
- When enabled=False the middleware is a transparent pass-through

Uses httpx.ASGITransport (no server) with a minimal FastAPI app — same
pattern as test_logging_middleware.py.  All tests create a fresh middleware
instance so counters don't leak between tests.

@decision DEC-SEC-001
@title In-memory sliding window rate limiter — test coverage
@status accepted
@rationale Validates per-IP counter logic, path-based limit selection, 429
    short-circuit response (including Retry-After header), the enabled=False
    bypass path, and the /api/auth/me carve-out (DEC-SEC-003).  No mocks of
    internal modules — tests operate on the real implementation via real ASGI
    dispatch.
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

    @app.get("/api/auth/me")
    async def auth_me() -> PlainTextResponse:
        return PlainTextResponse("profile")

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


@pytest.mark.asyncio
async def test_auth_me_not_blocked_by_auth_bucket():
    """
    /api/auth/me uses the api bucket limit, not the auth bucket (DEC-SEC-003).

    The middleware has a single per-IP deque shared across all paths.  The
    path-based limit selection determines *which ceiling* applies to that
    request, not which counter is incremented.  So the observable proof is:

    - With auth_requests_per_minute=2 and api_requests_per_minute=5,
      hitting /api/auth/me 5 times stays 200 the whole way (ceiling is 5).
    - Hitting /api/auth/login 2+1 times in a fresh client 429s on the 3rd
      (ceiling is 2).

    Each assertion uses a separate app+client pair to keep counters clean.
    """
    # Part 1 — /me respects the *api* ceiling, not the tight auth ceiling.
    cfg_me = _cfg(
        enabled=True,
        auth_requests_per_minute=2,   # would 429 on request 3 if /me used this
        api_requests_per_minute=5,
    )
    app_me = _make_app(cfg_me)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_me), base_url="http://test"
    ) as client:
        for i in range(5):  # 5 == api_requests_per_minute; all must be 200
            r = await client.get("/api/auth/me")
            assert r.status_code == 200, (
                f"/api/auth/me request {i+1} returned {r.status_code}; "
                "expected 200 — /me must use the api bucket (ceiling=5), "
                "not the auth bucket (ceiling=2)"
            )

    # Part 2 — /login still uses the tight auth ceiling (fresh app+client).
    cfg_login = _cfg(
        enabled=True,
        auth_requests_per_minute=2,
        api_requests_per_minute=100,
    )
    app_login = _make_app(cfg_login)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_login), base_url="http://test"
    ) as client:
        for _ in range(2):
            r = await client.post("/api/auth/login")
            assert r.status_code == 200

        r = await client.post("/api/auth/login")
        assert r.status_code == 429, (
            "/api/auth/login should still be rate-limited by the auth bucket (ceiling=2)"
        )


@pytest.mark.asyncio
async def test_auth_me_counts_against_api_bucket():
    """
    /api/auth/me requests DO count — they just count against the api bucket.

    Set api_requests_per_minute=3.  After 3 /me calls the api bucket is
    exhausted and the 4th /me returns 429.
    """
    cfg = _cfg(
        enabled=True,
        auth_requests_per_minute=100,
        api_requests_per_minute=3,
    )
    app = _make_app(cfg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for i in range(3):
            r = await client.get("/api/auth/me")
            assert r.status_code == 200, f"/api/auth/me request {i+1} should be 200"

        # 4th /me hits the api bucket ceiling
        r = await client.get("/api/auth/me")
        assert r.status_code == 429, (
            "/api/auth/me should 429 once the api bucket is full"
        )
        assert r.headers.get("retry-after") == "60"
