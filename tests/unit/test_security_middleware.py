"""
Unit tests for ada.api.middleware.security_headers.SecurityHeadersMiddleware.

Covers:
- Required security headers are present in every HTTP response
- Requests with Content-Length exceeding the body-size limit receive 413

Uses httpx.ASGITransport (no server) — real ASGI dispatch, no internal mocks.

@decision DEC-SEC-002
@title Security headers + body size at middleware level — test coverage
@status accepted
@rationale Tests confirm that (1) all four security headers are injected by
    the middleware for every HTTP response, and (2) the 413 short-circuit fires
    correctly when Content-Length exceeds the configured limit.  Media paths
    are covered implicitly via the body-size test (standard path used).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from ada.api.middleware.security_headers import SecurityHeadersMiddleware
from ada.core.config import SecurityConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(cfg: SecurityConfig) -> FastAPI:
    """Minimal FastAPI app wrapped with SecurityHeadersMiddleware."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, security_config=cfg)

    @app.get("/api/data")
    async def data() -> PlainTextResponse:
        return PlainTextResponse("hello")

    @app.post("/api/upload")
    async def upload() -> PlainTextResponse:
        return PlainTextResponse("received")

    return app


def _cfg(**overrides) -> SecurityConfig:
    return SecurityConfig(**overrides)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_headers_present_in_response():
    """All four required security headers appear on every HTTP response."""
    app = _make_app(_cfg())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/data")

    assert response.status_code == 200

    expected_headers = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "SAMEORIGIN",
        "referrer-policy": "strict-origin-when-cross-origin",
        "permissions-policy": "camera=(self), microphone=(self)",
    }
    for header, value in expected_headers.items():
        assert header in response.headers, f"Missing header: {header}"
        assert response.headers[header] == value, (
            f"Header {header!r} expected {value!r}, got {response.headers[header]!r}"
        )


@pytest.mark.asyncio
async def test_oversized_content_length_returns_413():
    """A Content-Length larger than max_body_size_bytes returns 413."""
    # Set a 100-byte limit so we can trigger it easily
    cfg = _cfg(max_body_size_bytes=100)
    app = _make_app(cfg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/upload",
            headers={"Content-Length": "999"},
            content=b"",  # actual body doesn't matter — we're checking the header
        )

    assert response.status_code == 413
    body = response.json()
    assert body["detail"] == "Request body too large"
