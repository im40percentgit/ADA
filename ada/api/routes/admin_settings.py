"""
Admin LLM-mode settings endpoint (Phase 15+ AI Stack Upgrade).

  GET  /api/admin/settings/llm-mode  -- return current mode + routing info
  PUT  /api/admin/settings/llm-mode  -- persist new mode; hot-swap router

@decision DEC-LLM-005
@title Three-mode LLM selector: claude / offline / dual
@status accepted
@rationale See ada/llm/router.py for full rationale. This endpoint is the
    runtime control surface: it writes the chosen mode to the system_settings
    table (persistent across restarts) and signals AgentRegistry to rebuild
    the router atomically. In-flight LLM calls finish on the old provider;
    new calls use the new router. Auth: caregiver-only (JWT required).

@decision DEC-LLM-008
@title GET /llm-mode returns effective agent_mapping from the live router
@status accepted
@rationale The original implementation returned config.model_routing.agent_mapping
    (the static TOML mapping) regardless of the active mode. In claude mode all
    agents should appear mapped to claude tiers; in offline mode all agents appear
    as offline_tier. Returning the static TOML mapping made the Settings UI show
    identical routing for all three modes.
    Fix: read the effective mapping from the live router via
    registry._router.list_profiles() + registry._router.provider_names. The
    live router's _agent_mapping is rebuilt by the mode-specific builder
    (_build_claude_only_router, _build_offline_router, _build_dual_router) so
    it always reflects the actual routing decisions in flight. When no registry
    is available (bootstrap race), fall back to static TOML.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.llm.router import create_model_router
from ada.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])

_VALID_MODES = {"claude", "offline", "dual"}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class LLMModeResponse(BaseModel):
    mode: str
    profiles: list[str]
    agent_mapping: dict[str, str]


class LLMModeUpdate(BaseModel):
    mode: str

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in _VALID_MODES:
            raise ValueError(f"mode must be one of {_VALID_MODES}, got {v!r}")
        return v


class LLMModeUpdateResponse(BaseModel):
    mode: str
    applied_at: str


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _state(request: Request) -> StateManager:
    return request.app.state.state_manager


def _config(request: Request) -> Any:
    return request.app.state.config


def _registry(request: Request) -> Any:
    return request.app.state.registry


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/llm-mode", response_model=LLMModeResponse)
async def get_llm_mode(
    request: Request,
    state: StateManager = Depends(_state),
    config: Any = Depends(_config),
    current_user: User = Depends(get_current_user),
) -> LLMModeResponse:
    """Return the current LLM mode and routing details.

    Mode resolution order: system_settings DB > ADA_LLM__MODE env > TOML > default.
    The response includes the *effective* agent_mapping from the live router
    (not the static TOML mapping), so the Settings UI shows the actual per-agent
    routing that is currently in flight (DEC-LLM-008).
    """
    db_mode = await state.get_system_setting("llm_mode")
    effective_mode = db_mode if db_mode in _VALID_MODES else config.llm.mode

    # Prefer the live router's effective mapping (reflects current mode).
    # Fall back to static TOML config when registry is not yet available.
    registry = _registry(request)
    live_router = getattr(registry, "_router", None)
    if live_router is not None:
        effective_agent_mapping = live_router.list_profiles()
        effective_profiles = live_router.provider_names
    elif config.model_routing:
        effective_agent_mapping = config.model_routing.agent_mapping
        effective_profiles = list(config.model_routing.profiles.keys())
    else:
        effective_agent_mapping = {}
        effective_profiles = []

    return LLMModeResponse(
        mode=effective_mode,
        profiles=effective_profiles,
        agent_mapping=effective_agent_mapping,
    )


@router.put("/llm-mode", response_model=LLMModeUpdateResponse)
async def set_llm_mode(
    request: Request,
    body: LLMModeUpdate,
    state: StateManager = Depends(_state),
    config: Any = Depends(_config),
    current_user: User = Depends(get_current_user),
) -> LLMModeUpdateResponse:
    """Persist new LLM mode and hot-swap the router.

    Side effects:
    1. Writes mode to system_settings table (survives restart).
    2. Rebuilds ModelRouter with the new mode.
    3. Calls registry.refresh_providers() which replaces _router AND
       re-resolves _llm on every already-registered agent so running
       agents use the new provider on their next call (DEC-LLM-009).

    In-flight LLM calls finish on the old provider — this is intentional
    and documented in DEC-LLM-005.
    """
    new_mode = body.mode

    # Persist to DB first so the choice survives restart
    await state.set_system_setting("llm_mode", new_mode)
    logger.info("admin_settings: llm_mode -> %s (set by user_id=%s)", new_mode, current_user.id)

    # Hot-swap: build new router, then update the registry + all running agents.
    # refresh_providers() atomically replaces registry._router AND re-resolves
    # _llm on each registered agent so the mode change affects in-flight chat
    # sessions, not just future agent registrations. (DEC-LLM-009)
    registry = _registry(request)
    new_router = create_model_router(config, db_mode=new_mode)
    registry.refresh_providers(new_router)
    logger.info("admin_settings: router + agents hot-swapped to mode=%s", new_mode)

    applied_at = datetime.now(timezone.utc).isoformat()
    return LLMModeUpdateResponse(mode=new_mode, applied_at=applied_at)
