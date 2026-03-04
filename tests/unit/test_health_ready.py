"""
Unit tests for the /health/ready FastAPI endpoint.

The endpoint probes the database by issuing a ``SELECT 1`` against the
connection held by ``app.state.state_manager._conn``.  A 200 with
``{"status": "ready"}`` indicates the DB is reachable; a 503 with
``{"status": "degraded"}`` indicates a failure.

Tests inject ``app.state.state_manager`` directly (bypassing lifespan) so
they run with zero infrastructure.  httpx.ASGITransport handles ASGI dispatch
without starting a real server.

@decision DEC-SEC-002
@title /health/ready — readiness probe for DB availability
@status accepted
@rationale Kubernetes / load balancer readiness checks need a signal that the
    database connection is alive, not just that the process is running.
    The endpoint re-uses the existing StateManager connection so it doesn't
    open a second connection.  State is injected directly in tests because
    httpx.ASGITransport does not run the FastAPI lifespan by default.
"""

from __future__ import annotations

import types

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockConn:
    """Fake aiosqlite connection that either succeeds or raises on execute."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def execute(self, sql: str):
        if self._fail:
            raise RuntimeError("DB connection lost")
        return None


def _make_app() -> FastAPI:
    """Minimal app with only the /health/ready endpoint."""
    app = FastAPI()

    @app.get("/health/ready")
    async def health_ready(request: Request) -> JSONResponse:
        """Readiness check — verifies DB connection is accessible."""
        try:
            sm = request.app.state.state_manager
            await sm._conn.execute("SELECT 1")
            return JSONResponse({"status": "ready", "checks": {"database": "ok"}})
        except Exception as exc:
            return JSONResponse(
                {"status": "degraded", "checks": {"database": f"error: {exc}"}},
                status_code=503,
            )

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_ready_returns_200_when_db_accessible():
    """Returns 200 with status=ready when the DB execute() succeeds."""
    app = _make_app()
    # Inject state directly — no lifespan needed for unit tests
    app.state.state_manager = types.SimpleNamespace(_conn=_MockConn(fail=False))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_returns_503_when_db_unavailable():
    """Returns 503 with status=degraded when execute() raises."""
    app = _make_app()
    app.state.state_manager = types.SimpleNamespace(_conn=_MockConn(fail=True))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert "error" in body["checks"]["database"]
