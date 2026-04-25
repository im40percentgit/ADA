"""
Game telemetry ingest endpoint — Phase 15+ Milestone 1.

POST /api/games/solitaire/event receives telemetry events emitted by the
React solitaire game, persists them to game_sessions, and publishes them
to the EventBus so downstream agents can subscribe.

Accepted event types:
  - game.session_start
  - game.session_end
  - game.hand_completed
  - game.engagement_streak

Auth: standard JWT bearer (require_patient_access or require_auth).
The patient_id comes from the authenticated user's linked patient record;
if missing (clinician/admin), the endpoint rejects with 400 so game data
is never written under a non-patient account.

@decision DEC-GAMES-001
@title Solitaire integrated as native React component, not iframe
@status accepted
@rationale Direct React integration is cleaner and smaller than an iframe
    + postMessage bridge. The game engine is pure TS with no DOM coupling,
    so it slots naturally into the existing component tree. No cross-origin
    messaging infrastructure is needed.

@decision DEC-GAMES-005
@title game_sessions table with JSON payload column
@status accepted
@rationale A JSON payload column accommodates the four current event shapes
    (session_start, session_end, hand_completed, engagement_streak) and
    future M3 verdict inputs without a schema migration. Pattern is
    consistent with existing notification_log and board_items in state.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from ada.api.auth import get_current_user
from ada.core.events import (
    EventTypes,
    GameEngagementStreakEvent,
    GameHandCompletedEvent,
    GameSessionEndEvent,
    GameSessionStartEvent,
)
from ada.models.user import User

router = APIRouter(tags=["games"])

# ---------------------------------------------------------------------------
# Allowed event types
# ---------------------------------------------------------------------------

_ALLOWED_EVENT_TYPES = {
    EventTypes.GAME_SESSION_START,
    EventTypes.GAME_SESSION_END,
    EventTypes.GAME_HAND_COMPLETED,
    EventTypes.GAME_ENGAGEMENT_STREAK,
}


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class GameEventRequest(BaseModel):
    """Inbound telemetry event from the solitaire frontend."""

    event_type: str
    occurred_at: str          # ISO-8601 timestamp (patient-local or UTC)
    payload: dict[str, Any]   # Event-specific fields — validated by type below

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in _ALLOWED_EVENT_TYPES:
            raise ValueError(
                f"Unknown event_type '{v}'. Allowed: {sorted(_ALLOWED_EVENT_TYPES)}"
            )
        return v

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("occurred_at must be a valid ISO-8601 timestamp")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(request: Request):
    return request.app.state.state_manager


def _bus(request: Request):
    return request.app.state.bus


def _build_domain_event(
    event_type: str,
    patient_id: str,
    payload: dict[str, Any],
) -> Any:
    """Construct the correct AdaEvent subclass for the given event_type."""
    game_session_id = payload.get("game_session_id", "")
    deck = payload.get("deck", "corgi")

    if event_type == EventTypes.GAME_SESSION_START:
        return GameSessionStartEvent(
            patient_id=patient_id,
            game_session_id=game_session_id,
            deck=deck,
        )
    if event_type == EventTypes.GAME_SESSION_END:
        return GameSessionEndEvent(
            patient_id=patient_id,
            game_session_id=game_session_id,
            duration_ms=payload.get("duration_ms", 0),
            completed_hands=payload.get("completed_hands", 0),
            error_count=payload.get("error_count", 0),
            end_reason=payload.get("end_reason", ""),
            deck=deck,
        )
    if event_type == EventTypes.GAME_HAND_COMPLETED:
        return GameHandCompletedEvent(
            patient_id=patient_id,
            game_session_id=game_session_id,
            hand_outcome=payload.get("hand_outcome", ""),
            error_count=payload.get("error_count", 0),
            duration_ms=payload.get("duration_ms", 0),
        )
    if event_type == EventTypes.GAME_ENGAGEMENT_STREAK:
        return GameEngagementStreakEvent(
            patient_id=patient_id,
            current_streak_days=payload.get("current_streak_days", 0),
            broken_streak=payload.get("broken_streak", False),
        )
    raise ValueError(f"Unhandled event_type: {event_type}")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/games/solitaire/event", status_code=201)
async def ingest_game_event(
    body: GameEventRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Ingest a single solitaire telemetry event.

    Persists the event to the game_sessions table and publishes it to the
    EventBus. The patient_id is resolved from the authenticated user's
    linked patient record — if the user has no linked patient the request
    is rejected.

    Returns the inserted row id on success.
    """
    patient_id = current_user.patient_id
    if not patient_id:
        raise HTTPException(
            status_code=400,
            detail="No patient linked to this account. Game events require a patient-linked user.",
        )

    state = _state(request)

    # Verify patient exists
    patient = await state.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Persist to DB
    record = {
        "patient_id": patient_id,
        "event_type": body.event_type,
        "payload": body.payload,
        "occurred_at": body.occurred_at,
    }
    row_id = await state.create_game_session_event(record)

    # Publish to EventBus (non-blocking — subscribers handle asynchronously)
    bus = _bus(request)
    domain_event = _build_domain_event(body.event_type, patient_id, body.payload)
    await bus.publish(domain_event)

    return {"id": row_id, "status": "accepted"}
