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
    The response includes the live agent_mapping so the Settings UI can render
    the per-agent routing panel in dual mode.
    """
    db_mode = await state.get_system_setting("llm_mode")
    effective_mode = db_mode if db_mode in _VALID_MODES else config.llm.mode

    routing_info: dict[str, Any] = {}
    if config.model_routing:
        routing_info = {
            "profiles": list(config.model_routing.profiles.keys()),
            "agent_mapping": config.model_routing.agent_mapping,
        }
    else:
        routing_info = {"profiles": [], "agent_mapping": {}}

    return LLMModeResponse(
        mode=effective_mode,
        profiles=routing_info["profiles"],
        agent_mapping=routing_info["agent_mapping"],
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
    3. Atomically replaces the router on AgentRegistry so the next
       get_provider() call uses the new routing rules.

    In-flight LLM calls finish on the old provider — this is intentional
    and documented in DEC-LLM-005.
    """
    new_mode = body.mode

    # Persist to DB first so the choice survives restart
    await state.set_system_setting("llm_mode", new_mode)
    logger.info("admin_settings: llm_mode -> %s (set by user_id=%s)", new_mode, current_user.id)

    # Hot-swap router: build new router with the updated mode, then swap
    # the reference on the registry. In-flight calls hold a reference to the
    # old provider and complete normally; new calls go through the new router.
    registry = _registry(request)
    new_router = create_model_router(config, db_mode=new_mode)
    # AgentRegistry stores the router as _router. Atomic replacement: in-flight
    # calls hold a reference to the old provider and complete normally; new
    # get_provider() calls go through the new router. (DEC-LLM-005)
    registry._router = new_router
    logger.info("admin_settings: router hot-swapped to mode=%s", new_mode)

    applied_at = datetime.now(timezone.utc).isoformat()
    return LLMModeUpdateResponse(mode=new_mode, applied_at=applied_at)
