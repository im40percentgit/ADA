"""
FastAPI application factory for Ada.

Creates and configures the app with CORS, routes, and lifespan management.
The app is wired to shared infrastructure (bus, state, registry) via
app.state so routes can access them via request.app.state.

Middleware stack (outermost to innermost):
  1. CORSMiddleware        — preflight / origin checks
  2. SecurityHeadersMiddleware — security response headers + body size limits
  3. RateLimitMiddleware   — per-IP sliding window rate limiting (when enabled)
  4. StructlogRequestMiddleware — request_id correlation + access logging

@decision DEC-API-001
@title JWT auth placeholder only in Phase 1 — superseded by DEC-AUTH-001/002
@status superseded
@rationale Phase 1 placeholder replaced by real JWT auth in Phase 2.
    See ada/api/auth.py for the full implementation.

@decision DEC-SEC-001
@title In-memory sliding window rate limiter (no Redis)
@status accepted
@rationale Single-process deployment. See ada/api/middleware/rate_limit.py.

@decision DEC-SEC-002
@title Security headers + body size at middleware level
@status accepted
@rationale Defense-in-depth. See ada/api/middleware/security_headers.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ada.api.middleware.logging import StructlogRequestMiddleware
from ada.api.middleware.rate_limit import RateLimitMiddleware
from ada.api.middleware.security_headers import SecurityHeadersMiddleware
from ada.api.routes import alerts, appointments, assessments, audit_log, auth, boards, caregiver, chat, circles, clinician_notes, cognitive, companion, consent, daily_summaries, data_export, games, knowledge, media, medications, notifications, onboarding, organizations, password_reset, patients, prescribing_notes, progress_report, retention, screening_interact, sessions, simulator, treatment_plans
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.agents.registry import AgentRegistry


def create_app(
    config: AdaConfig,
    bus: EventBus,
    state: StateManager,
    registry: AgentRegistry,
    *,
    tts_agent: object | None = None,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        config: Ada configuration.
        bus: Running EventBus instance.
        state: Initialised StateManager.
        registry: AgentRegistry with started agents.

    Returns:
        Configured FastAPI application ready to serve.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup
        app.state.bus = bus
        app.state.state_manager = state
        app.state.registry = registry
        app.state.config = config
        app.state.tts_agent = tts_agent
        yield
        # Shutdown — caller (main.py) is responsible for stopping bus/state/agents

    app = FastAPI(
        title="Ada Mental Health API",
        version="0.1.0",
        description="Multi-agent mental health AI system API",
        lifespan=lifespan,
    )

    # Note: in Starlette, add_middleware wraps — the LAST call added is the
    # OUTERMOST layer. We want: CORS > SecurityHeaders > RateLimit > Structlog.
    # So we add them in reverse order: innermost first.

    # Innermost: request tracing — assigns request_id, emits structured access log
    app.add_middleware(StructlogRequestMiddleware, logging_config=config.logging)

    # Rate limiting — per-IP sliding window (conditional on enabled flag)
    if config.rate_limit.enabled:
        app.add_middleware(RateLimitMiddleware, rate_limit_config=config.rate_limit)

    # Security headers + body size enforcement
    app.add_middleware(SecurityHeadersMiddleware, security_config=config.security)

    # Outermost: CORS — strict allow-lists from config (no wildcards).
    # Merge api.cors_origins with network.cors_origins so the LAN dev script
    # can add extra origins (e.g. http://192.168.1.x:5173) without losing
    # the default localhost origin.
    _cors_origins = list({*config.api.cors_origins, *config.network.cors_origins})
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=config.security.cors_allow_methods,
        allow_headers=config.security.cors_allow_headers,
    )

    # Routers
    app.include_router(auth.router)           # /api/auth/*
    app.include_router(password_reset.router) # /api/auth/forgot-password, /api/auth/reset-password
    app.include_router(chat.router)
    app.include_router(media.router)        # /ws/media/*
    app.include_router(media.rest_router)   # /api/sessions/*/sensor|audio|video-frame
    app.include_router(patients.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(assessments.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")
    app.include_router(medications.router, prefix="/api")
    app.include_router(cognitive.router, prefix="/api")
    app.include_router(screening_interact.router, prefix="/api")  # /api/patients/*/screenings/start, /api/screenings/*/respond
    app.include_router(appointments.router, prefix="/api")
    app.include_router(simulator.router)   # /api/sessions/*/simulator/start|stop
    app.include_router(caregiver.router, prefix="/api")  # /api/caregiver/*
    app.include_router(circles.router, prefix="/api")   # /api/circles/*
    app.include_router(boards.router, prefix="/api")   # /api/boards/* + /api/circles/*/boards
    app.include_router(boards.ws_router)               # /ws/board/*
    app.include_router(alerts.router)                  # /api/alerts/*
    app.include_router(notifications.router, prefix="/api")    # /api/notifications/*
    app.include_router(clinician_notes.router, prefix="/api")  # /api/notes/*
    app.include_router(daily_summaries.router, prefix="/api")  # /api/patients/*/daily-summaries/*
    app.include_router(progress_report.router, prefix="/api")  # /api/patients/*/progress-report
    app.include_router(companion.router, prefix="/api")          # /api/companion/*
    app.include_router(onboarding.router, prefix="/api")         # /api/onboarding/*
    app.include_router(organizations.router, prefix="/api")      # /api/organizations/*
    app.include_router(prescribing_notes.router, prefix="/api") # /api/patients/*/prescribing-notes
    app.include_router(treatment_plans.router, prefix="/api")  # /api/treatment-plans/*, /api/patients/*/treatment-plans
    app.include_router(data_export.router, prefix="/api")     # /api/patients/*/export/*
    app.include_router(consent.router, prefix="/api")         # /api/consent
    app.include_router(audit_log.router, prefix="/api")       # /api/audit-log
    app.include_router(retention.router, prefix="/api")       # /api/admin/retention
    app.include_router(games.router, prefix="/api")          # /api/games/solitaire/event

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

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
