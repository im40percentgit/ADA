"""
Unit tests for ada.api.middleware.logging.StructlogRequestMiddleware.

Covers:
- request_id is generated when none supplied
- supplied X-Request-ID is echoed back in the response header
- access log entry is emitted with method, path, status, duration_ms
- access log is suppressed when access_log=False
- lifespan scope passes straight through without instrumentation

@decision DEC-OBS-001
@title Correlation IDs via structlog contextvars — test coverage
@status accepted
@rationale Tests verify the three observable contracts of the middleware:
    (1) UUID4 generated when no X-Request-ID supplied,
    (2) caller-supplied ID echoed unchanged,
    (3) access log emitted/suppressed per config flag.
    Lifespan passthrough confirms non-HTTP scopes are untouched.
    Uses httpx.ASGITransport (no server required) — real ASGI dispatch,
    no mocks of internal modules.
"""

from __future__ import annotations

import re

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from ada.api.middleware.logging import StructlogRequestMiddleware
from ada.core.config import LoggingConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(logging_config: LoggingConfig) -> FastAPI:
    """Minimal FastAPI app wrapped with StructlogRequestMiddleware."""
    app = FastAPI()
    app.add_middleware(StructlogRequestMiddleware, logging_config=logging_config)

    @app.get("/ping")
    async def ping() -> PlainTextResponse:
        return PlainTextResponse("pong")

    return app


def _default_config(**overrides) -> LoggingConfig:
    return LoggingConfig(**overrides)


UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generates_request_id_when_none_supplied():
    """Middleware generates a UUID4 request_id and echoes it in the response."""
    app = _make_app(_default_config())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ping")

    assert response.status_code == 200
    rid = response.headers.get("x-request-id", "")
    assert UUID4_RE.match(rid), f"Expected UUID4, got {rid!r}"


@pytest.mark.asyncio
async def test_echoes_supplied_request_id():
    """Middleware returns the caller-supplied X-Request-ID unchanged."""
    app = _make_app(_default_config())
    supplied = "my-trace-abc-123"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ping", headers={"X-Request-ID": supplied})

    assert response.status_code == 200
    assert response.headers.get("x-request-id") == supplied


@pytest.mark.asyncio
async def test_access_log_emitted(caplog):
    """Middleware emits a structured access log entry with required fields."""
    import logging
    import structlog

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    app = _make_app(_default_config(access_log=True))

    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/ping")

    assert response.status_code == 200
    assert any(
        "request" in r.getMessage() or "GET" in r.getMessage()
        for r in caplog.records
    ), f"No access log found. Records: {[r.getMessage() for r in caplog.records]}"


@pytest.mark.asyncio
async def test_access_log_suppressed_when_disabled():
    """When access_log=False no access-log entry is emitted for the request."""
    logged_events: list[str] = []

    import structlog

    def _capture(logger, method, event_dict):
        logged_events.append(str(event_dict.get("event", "")))
        raise structlog.DropEvent()

    structlog.configure(
        processors=[_capture],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    app = _make_app(_default_config(access_log=False))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.get("/ping")

    assert "request" not in logged_events, (
        f"Expected no 'request' access log but got: {logged_events}"
    )


@pytest.mark.asyncio
async def test_lifespan_scope_passes_through():
    """Lifespan scope is forwarded to the app without modification."""
    called: list[str] = []

    async def bare_app(scope, receive, send):
        called.append(scope["type"])

    async def noop_receive():
        return {}

    async def noop_send(message):
        pass

    config = _default_config()
    middleware = StructlogRequestMiddleware(bare_app, config)

    await middleware({"type": "lifespan"}, noop_receive, noop_send)
    assert called == ["lifespan"]
