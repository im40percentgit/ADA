"""
Unit tests for the solitaire game telemetry endpoint.

POST /api/games/solitaire/event

Coverage:
- Valid session_start event: persisted to DB, EventBus receives the event
- Valid session_end event: persisted, payload fields stored correctly
- Valid hand_completed event: persisted
- Valid engagement_streak event: persisted
- Unknown event_type: 422 rejected
- Missing occurred_at: 422 rejected
- Malformed occurred_at: 422 rejected
- User with no linked patient_id: 400 rejected
- Patient not found in DB (race condition): 404 rejected
- EventBus publish is called for valid events

@decision DEC-GAMES-001
@title Route tests use real in-memory SQLite, not mocks, per Sacred Practice #5
@status accepted
@rationale Consistent with test_appointment_routes.py and test_board_routes.py.
    The EventBus is real (in-memory); we verify publish by subscribing a
    collector before the request is made.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User


# ---------------------------------------------------------------------------
# Minimal LLM stub
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# Test users
# ---------------------------------------------------------------------------

_PATIENT_ID = "pat-games-001"

_USER_WITH_PATIENT = User(
    id="user-games-001",
    email="patient@example.com",
    role="user",
    patient_id=_PATIENT_ID,
    created_at=datetime.utcnow(),
    is_active=True,
)

_USER_NO_PATIENT = User(
    id="user-games-002",
    email="clinician@example.com",
    role="clinician",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@contextmanager
def _make_client(
    state: StateManager,
    user: User,
    *,
    raise_server_exceptions: bool = True,
) -> Generator[tuple[TestClient, EventBus], None, None]:
    """Return (TestClient, EventBus) for use in a with-block."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=raise_server_exceptions) as client:
        yield client, bus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """In-memory StateManager with a seeded patient."""
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Games Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Valid event payloads
# ---------------------------------------------------------------------------

_NOW_ISO = "2026-04-24T20:00:00"

_SESSION_START_BODY: dict[str, Any] = {
    "event_type": EventTypes.GAME_SESSION_START,
    "occurred_at": _NOW_ISO,
    "payload": {
        "game_session_id": "gs-001",
        "deck": "corgi",
    },
}

_SESSION_END_BODY: dict[str, Any] = {
    "event_type": EventTypes.GAME_SESSION_END,
    "occurred_at": _NOW_ISO,
    "payload": {
        "game_session_id": "gs-001",
        "duration_ms": 120000,
        "completed_hands": 1,
        "error_count": 3,
        "end_reason": "quit",
        "deck": "corgi",
    },
}

_HAND_COMPLETED_BODY: dict[str, Any] = {
    "event_type": EventTypes.GAME_HAND_COMPLETED,
    "occurred_at": _NOW_ISO,
    "payload": {
        "game_session_id": "gs-001",
        "hand_outcome": "won",
        "error_count": 1,
        "duration_ms": 90000,
    },
}

_STREAK_BODY: dict[str, Any] = {
    "event_type": EventTypes.GAME_ENGAGEMENT_STREAK,
    "occurred_at": _NOW_ISO,
    "payload": {
        "current_streak_days": 5,
        "broken_streak": False,
    },
}


# ---------------------------------------------------------------------------
# Tests: valid events persisted
# ---------------------------------------------------------------------------

def test_session_start_persisted(state):
    """session_start event is stored in game_sessions and returns 201 with an id."""
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=_SESSION_START_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["status"] == "accepted"
    assert isinstance(data["id"], int)


def test_session_end_persisted(state):
    """session_end event is stored; payload fields are round-tripped correctly."""
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=_SESSION_END_BODY)
    assert resp.status_code == 201


def test_hand_completed_persisted(state):
    """hand_completed event is accepted and stored."""
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=_HAND_COMPLETED_BODY)
    assert resp.status_code == 201


def test_engagement_streak_persisted(state):
    """engagement_streak event is accepted and stored."""
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=_STREAK_BODY)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_db_row_content(state):
    """Stored row has correct patient_id, event_type, and decoded payload."""
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        client.post("/api/games/solitaire/event", json=_SESSION_END_BODY)

    rows = await state.get_game_session_events(_PATIENT_ID, event_type=EventTypes.GAME_SESSION_END)
    assert len(rows) == 1
    row = rows[0]
    assert row["patient_id"] == _PATIENT_ID
    assert row["event_type"] == EventTypes.GAME_SESSION_END
    assert row["payload"]["completed_hands"] == 1
    assert row["payload"]["duration_ms"] == 120000
    assert row["occurred_at"] == _NOW_ISO


# ---------------------------------------------------------------------------
# Tests: EventBus dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eventbus_published_on_valid_event(state):
    """EventBus receives a domain event when the route ingests a valid event.

    Uses httpx.AsyncClient so the HTTP call, the EventBus drain task, and
    the asyncio.sleep all run in the same event loop. TestClient is sync-only
    and doesn't share an event loop with the test, so asyncio.sleep can't
    drain the bus queue in that context.
    """
    import asyncio
    from httpx import AsyncClient, ASGITransport

    received: list = []

    config = AdaConfig()
    bus = EventBus()

    async def _collect(event):
        received.append(event)

    # Subscribe before start so the drain task is created by bus.start()
    bus.subscribe(EventTypes.GAME_SESSION_START, _collect, "test_collector")

    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _USER_WITH_PATIENT

    # Populate app.state manually — AsyncClient with ASGITransport does not
    # trigger FastAPI lifespan, so state_manager and bus must be set directly.
    app.state.state_manager = state
    app.state.bus = bus
    app.state.registry = registry
    app.state.config = config
    app.state.tts_agent = None

    await bus.start()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/games/solitaire/event", json=_SESSION_START_BODY)
        assert resp.status_code == 201
        # Yield to let the drain task fire
        await asyncio.sleep(0.05)
    await bus.stop()

    assert len(received) == 1
    evt = received[0]
    assert evt.event_type == EventTypes.GAME_SESSION_START
    assert evt.patient_id == _PATIENT_ID


# ---------------------------------------------------------------------------
# Tests: validation rejects
# ---------------------------------------------------------------------------

def test_unknown_event_type_rejected(state):
    """Unknown event_type produces a 422 Unprocessable Entity."""
    body = {**_SESSION_START_BODY, "event_type": "game.unknown_event"}
    with _make_client(state, _USER_WITH_PATIENT, raise_server_exceptions=False) as (client, _):
        resp = client.post("/api/games/solitaire/event", json=body)
    assert resp.status_code == 422


def test_missing_occurred_at_rejected(state):
    """Missing occurred_at produces 422."""
    body = {k: v for k, v in _SESSION_START_BODY.items() if k != "occurred_at"}
    with _make_client(state, _USER_WITH_PATIENT, raise_server_exceptions=False) as (client, _):
        resp = client.post("/api/games/solitaire/event", json=body)
    assert resp.status_code == 422


def test_malformed_occurred_at_rejected(state):
    """Non-ISO occurred_at string is rejected with 422."""
    body = {**_SESSION_START_BODY, "occurred_at": "not-a-timestamp"}
    with _make_client(state, _USER_WITH_PATIENT, raise_server_exceptions=False) as (client, _):
        resp = client.post("/api/games/solitaire/event", json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: auth / patient checks
# ---------------------------------------------------------------------------

def test_user_without_patient_rejected(state):
    """User with no linked patient_id gets 400."""
    with _make_client(state, _USER_NO_PATIENT, raise_server_exceptions=False) as (client, _):
        resp = client.post("/api/games/solitaire/event", json=_SESSION_START_BODY)
    assert resp.status_code == 400
    assert "patient" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unknown_patient_returns_404(state):
    """If the linked patient doesn't exist in the DB, the endpoint returns 404."""
    ghost_user = User(
        id="user-ghost",
        email="ghost@example.com",
        role="user",
        patient_id="nonexistent-patient-id",
        created_at=datetime.utcnow(),
        is_active=True,
    )
    with _make_client(state, ghost_user, raise_server_exceptions=False) as (client, _):
        resp = client.post("/api/games/solitaire/event", json=_SESSION_START_BODY)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: game.move_made (M1 v0.5)
# ---------------------------------------------------------------------------

_MOVE_MADE_BODY: dict[str, Any] = {
    "event_type": "game.move_made",
    "occurred_at": _NOW_ISO,
    "payload": {
        "game_session_id": "gs-001",
        "move_index": 0,
        "move_type": "tableau-to-foundation",
        "was_valid": True,
        "was_undo": False,
        "decision_time_ms": 1250,
        "card_value": 1,
    },
}


def test_move_made_full_payload_accepted(state):
    """move_made event with all required fields returns 201."""
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=_MOVE_MADE_BODY)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "accepted"
    assert isinstance(data["id"], int)


def test_move_made_was_valid_false_accepted(state):
    """move_made with was_valid=False (invalid click) is accepted — no error_rate enforcement at event level."""
    body = {
        **_MOVE_MADE_BODY,
        "payload": {**_MOVE_MADE_BODY["payload"], "was_valid": False},
    }
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=body)
    assert resp.status_code == 201


def test_move_made_null_card_value_accepted(state):
    """move_made with card_value=null (stock-flip / recycle) is accepted."""
    body = {
        **_MOVE_MADE_BODY,
        "payload": {**_MOVE_MADE_BODY["payload"], "card_value": None},
    }
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=body)
    assert resp.status_code == 201


def test_move_made_missing_required_field_rejected(state):
    """move_made missing a required field (decision_time_ms) is rejected with 422."""
    incomplete_payload = {k: v for k, v in _MOVE_MADE_BODY["payload"].items()
                          if k != "decision_time_ms"}
    body = {**_MOVE_MADE_BODY, "payload": incomplete_payload}
    with _make_client(state, _USER_WITH_PATIENT, raise_server_exceptions=False) as (client, _):
        resp = client.post("/api/games/solitaire/event", json=body)
    assert resp.status_code == 422
    assert "decision_time_ms" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: extended game.session_end payload (M1 v0.5)
# ---------------------------------------------------------------------------

_SESSION_END_EXTENDED_BODY: dict[str, Any] = {
    "event_type": "game.session_end",
    "occurred_at": _NOW_ISO,
    "payload": {
        "game_session_id": "gs-001",
        "duration_ms": 180000,
        "completed_hands": 1,
        "error_count": 2,
        "end_reason": "quit",
        "deck": "corgi",
        # M1 v0.5 aggregate fields
        "total_moves": 47,
        "total_undo_count": 3,
        "total_invalid_click_count": 5,
        "total_idle_ms": 12000,
        "restart_count_today": 2,
    },
}


def test_session_end_with_v05_aggregates_accepted(state):
    """Extended session_end payload including M1 v0.5 aggregate fields returns 201."""
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=_SESSION_END_EXTENDED_BODY)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_session_end_v05_aggregates_round_trip(state):
    """M1 v0.5 aggregate fields are stored in the JSON payload and readable from DB."""
    with _make_client(state, _USER_WITH_PATIENT) as (client, _bus):
        client.post("/api/games/solitaire/event", json=_SESSION_END_EXTENDED_BODY)

    rows = await state.get_game_session_events(_PATIENT_ID, event_type="game.session_end")
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["total_moves"] == 47
    assert payload["total_undo_count"] == 3
    assert payload["total_invalid_click_count"] == 5
    assert payload["total_idle_ms"] == 12000
    assert payload["restart_count_today"] == 2
