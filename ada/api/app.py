"""
FastAPI application factory for Ada.

Creates and configures the app with CORS, routes, and lifespan management.
The app is wired to shared infrastructure (bus, state, registry) via
app.state so routes can access them via request.app.state.

@decision DEC-API-001
@title JWT auth placeholder only in Phase 1 — superseded by DEC-AUTH-001/002
@status superseded
@rationale Phase 1 placeholder replaced by real JWT auth in Phase 2.
    See ada/api/auth.py for the full implementation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ada.api.routes import assessments, auth, chat, cognitive, knowledge, medications, patients, sessions
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.agents.registry import AgentRegistry


def create_app(
    config: AdaConfig,
    bus: EventBus,
    state: StateManager,
    registry: AgentRegistry,
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
        yield
        # Shutdown — caller (main.py) is responsible for stopping bus/state/agents

    app = FastAPI(
        title="Ada Mental Health API",
        version="0.1.0",
        description="Multi-agent mental health AI system API",
        lifespan=lifespan,
    )

    # CORS — restricted to configured origins (localhost only in Phase 1)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth.router)          # /api/auth/*
    app.include_router(chat.router)
    app.include_router(patients.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(assessments.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")
    app.include_router(medications.router, prefix="/api")
    app.include_router(cognitive.router, prefix="/api")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    return app
