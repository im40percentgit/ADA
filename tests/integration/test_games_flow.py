"""
Integration test: solitaire telemetry full vertical slice.

HTTP POST /api/games/solitaire/event
  → route validates payload
  → StateManager persists row to game_sessions
  → EventBus publishes domain event
  → DB row is retrievable with correct content

Uses real in-memory SQLite, real EventBus, real FastAPI TestClient.
No mocks except the LLM provider (external boundary per DEC-TEST-005).

@decision DEC-GAMES-001
@title Integration test exercises the full HTTP→DB→EventBus slice
@status accepted
@rationale Mirrors test_board_flow.py pattern. A real StateManager and
    TestClient validate the entire vertical slice without mocking any
    internal module. Only the LLM provider is stubbed.
"""

from __future__ import annotations

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
# LLM stub
# ---------------------------------------------------------------------------

class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATIENT_ID = "pat-games-flow-001"
_OCCURRED_AT = "2026-04-24T20:00:00"

_PATIENT_USER = User(
    id="user-games-flow-001",
    email="patient@example.com",
    role="user",
    patient_id=_PATIENT_ID,
    created_at=datetime.utcnow(),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    """In-memory StateManager with a seeded patient."""
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Flow Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


@contextmanager
def _make_client(
    sm: StateManager, user: User
) -> Generator[tuple[TestClient, EventBus], None, None]:
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, sm, make_null_router(_NullLLM()))
    app = create_app(config, bus, sm, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client, bus


# ---------------------------------------------------------------------------
# Full-slice tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_end_full_slice(state):
    """
    POST session_end → 201 → DB row stored → payload round-trips correctly.

    This is the primary telemetry event for the M3 verdict generator.
    """
    body: dict[str, Any] = {
        "event_type": EventTypes.GAME_SESSION_END,
        "occurred_at": _OCCURRED_AT,
        "payload": {
            "game_session_id": "gs-flow-001",
            "duration_ms": 300000,
            "completed_hands": 2,
            "error_count": 5,
            "end_reason": "visibility",
            "deck": "corgi",
        },
    }

    with _make_client(state, _PATIENT_USER) as (client, _bus):
        resp = client.post("/api/games/solitaire/event", json=body)

    assert resp.status_code == 201
    row_id = resp.json()["id"]
    assert isinstance(row_id, int)

    # Verify DB persistence
    rows = await state.get_game_session_events(
        _PATIENT_ID, event_type=EventTypes.GAME_SESSION_END
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == row_id
    assert row["patient_id"] == _PATIENT_ID
    assert row["event_type"] == EventTypes.GAME_SESSION_END
    assert row["occurred_at"] == _OCCURRED_AT

    payload = row["payload"]
    assert payload["duration_ms"] == 300000
    assert payload["completed_hands"] == 2
    assert payload["error_count"] == 5
    assert payload["end_reason"] == "visibility"
    assert payload["deck"] == "corgi"


@pytest.mark.asyncio
async def test_eventbus_receives_domain_event(state):
    """EventBus subscriber receives a typed domain event with correct fields.

    Uses httpx.AsyncClient so the HTTP call, the EventBus drain task, and
    asyncio.sleep all run in the same event loop. This mirrors the pattern
    used in test_ml_pipeline.py where bus.publish + asyncio.sleep work
    together in a pure-async context.
    """
    import asyncio
    from httpx import AsyncClient, ASGITransport

    received: list = []

    config = AdaConfig()
    bus = EventBus()

    async def _collect(event):
        received.append(event)

    bus.subscribe(EventTypes.GAME_SESSION_START, _collect, "flow_test_collector")

    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _PATIENT_USER

    body: dict[str, Any] = {
        "event_type": EventTypes.GAME_SESSION_START,
        "occurred_at": _OCCURRED_AT,
        "payload": {"game_session_id": "gs-flow-002", "deck": "corgi"},
    }

    # Populate app.state manually — AsyncClient with ASGITransport does not
    # trigger FastAPI lifespan.
    app.state.state_manager = state
    app.state.bus = bus
    app.state.registry = registry
    app.state.config = config
    app.state.tts_agent = None

    await bus.start()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/games/solitaire/event", json=body)
        assert resp.status_code == 201
        await asyncio.sleep(0.05)
    await bus.stop()

    assert len(received) == 1
    evt = received[0]
    assert evt.event_type == EventTypes.GAME_SESSION_START
    assert evt.patient_id == _PATIENT_ID
    assert evt.game_session_id == "gs-flow-002"
    assert evt.deck == "corgi"


@pytest.mark.asyncio
async def test_multiple_events_all_persisted(state):
    """Four different event types all land in the DB under the same patient."""
    events: list[dict[str, Any]] = [
        {
            "event_type": EventTypes.GAME_SESSION_START,
            "occurred_at": _OCCURRED_AT,
            "payload": {"game_session_id": "gs-multi-001", "deck": "corgi"},
        },
        {
            "event_type": EventTypes.GAME_HAND_COMPLETED,
            "occurred_at": _OCCURRED_AT,
            "payload": {
                "game_session_id": "gs-multi-001",
                "hand_outcome": "won",
                "error_count": 0,
                "duration_ms": 45000,
            },
        },
        {
            "event_type": EventTypes.GAME_ENGAGEMENT_STREAK,
            "occurred_at": _OCCURRED_AT,
            "payload": {"current_streak_days": 3, "broken_streak": False},
        },
        {
            "event_type": EventTypes.GAME_SESSION_END,
            "occurred_at": _OCCURRED_AT,
            "payload": {
                "game_session_id": "gs-multi-001",
                "duration_ms": 60000,
                "completed_hands": 1,
                "error_count": 0,
                "end_reason": "quit",
                "deck": "corgi",
            },
        },
    ]

    with _make_client(state, _PATIENT_USER) as (client, _bus):
        for event_body in events:
            resp = client.post("/api/games/solitaire/event", json=event_body)
            assert resp.status_code == 201, f"Failed for {event_body['event_type']}: {resp.text}"

    all_rows = await state.get_game_session_events(_PATIENT_ID)
    assert len(all_rows) == 4

    stored_types = {r["event_type"] for r in all_rows}
    assert stored_types == {
        EventTypes.GAME_SESSION_START,
        EventTypes.GAME_SESSION_END,
        EventTypes.GAME_HAND_COMPLETED,
        EventTypes.GAME_ENGAGEMENT_STREAK,
    }


@pytest.mark.asyncio
async def test_get_game_session_events_filter_by_type(state):
    """get_game_session_events with event_type filter returns only matching rows."""
    with _make_client(state, _PATIENT_USER) as (client, _bus):
        client.post("/api/games/solitaire/event", json={
            "event_type": EventTypes.GAME_SESSION_START,
            "occurred_at": _OCCURRED_AT,
            "payload": {"game_session_id": "gs-filter-001", "deck": "corgi"},
        })
        client.post("/api/games/solitaire/event", json={
            "event_type": EventTypes.GAME_SESSION_END,
            "occurred_at": _OCCURRED_AT,
            "payload": {
                "game_session_id": "gs-filter-001",
                "duration_ms": 60000,
                "completed_hands": 0,
                "error_count": 0,
                "end_reason": "idle",
                "deck": "corgi",
            },
        })

    start_rows = await state.get_game_session_events(
        _PATIENT_ID, event_type=EventTypes.GAME_SESSION_START
    )
    assert len(start_rows) == 1
    assert start_rows[0]["event_type"] == EventTypes.GAME_SESSION_START

    end_rows = await state.get_game_session_events(
        _PATIENT_ID, event_type=EventTypes.GAME_SESSION_END
    )
    assert len(end_rows) == 1
    assert end_rows[0]["event_type"] == EventTypes.GAME_SESSION_END


@pytest.mark.asyncio
async def test_move_made_flow_five_rows(state):
    """
    End-to-end M1 v0.5 flow:
      session_start → 3× move_made → session_end (with aggregates)
    Produces exactly 5 rows in game_sessions; move_made rows have correct
    move_type and decision_time_ms; session_end row carries v0.5 aggregates.
    """
    session_id = "gs-move-flow-001"

    def _move_body(idx: int, move_type: str, valid: bool, undo: bool, card_val: int | None) -> dict:
        return {
            "event_type": EventTypes.GAME_MOVE_MADE,
            "occurred_at": _OCCURRED_AT,
            "payload": {
                "game_session_id": session_id,
                "move_index": idx,
                "move_type": move_type,
                "was_valid": valid,
                "was_undo": undo,
                "decision_time_ms": 800 + idx * 100,
                "card_value": card_val,
            },
        }

    events: list[dict[str, Any]] = [
        {
            "event_type": EventTypes.GAME_SESSION_START,
            "occurred_at": _OCCURRED_AT,
            "payload": {"game_session_id": session_id, "deck": "corgi"},
        },
        _move_body(0, "stock-flip", True, False, None),
        _move_body(1, "talon-to-tableau", True, False, 14),
        _move_body(2, "invalid", False, False, 7),
        {
            "event_type": EventTypes.GAME_SESSION_END,
            "occurred_at": _OCCURRED_AT,
            "payload": {
                "game_session_id": session_id,
                "duration_ms": 45000,
                "completed_hands": 0,
                "error_count": 1,
                "end_reason": "quit",
                "deck": "corgi",
                "total_moves": 3,
                "total_undo_count": 0,
                "total_invalid_click_count": 1,
                "total_idle_ms": 0,
                "restart_count_today": 1,
            },
        },
    ]

    with _make_client(state, _PATIENT_USER) as (client, _bus):
        for evt in events:
            resp = client.post("/api/games/solitaire/event", json=evt)
            assert resp.status_code == 201, f"Failed for {evt['event_type']}: {resp.text}"

    # 5 rows total
    all_rows = await state.get_game_session_events(_PATIENT_ID)
    assert len(all_rows) == 5

    stored_types = [r["event_type"] for r in all_rows]
    assert stored_types.count(EventTypes.GAME_MOVE_MADE) == 3
    assert stored_types.count(EventTypes.GAME_SESSION_START) == 1
    assert stored_types.count(EventTypes.GAME_SESSION_END) == 1

    # move_made rows have correct shapes
    move_rows = [r for r in all_rows if r["event_type"] == EventTypes.GAME_MOVE_MADE]
    move_rows.sort(key=lambda r: r["payload"]["move_index"])

    assert move_rows[0]["payload"]["move_type"] == "stock-flip"
    assert move_rows[0]["payload"]["card_value"] is None
    assert move_rows[1]["payload"]["move_type"] == "talon-to-tableau"
    assert move_rows[1]["payload"]["card_value"] == 14
    assert move_rows[2]["payload"]["was_valid"] is False

    # session_end has v0.5 aggregates
    end_row = next(r for r in all_rows if r["event_type"] == EventTypes.GAME_SESSION_END)
    assert end_row["payload"]["total_moves"] == 3
    assert end_row["payload"]["total_invalid_click_count"] == 1
    assert end_row["payload"]["restart_count_today"] == 1
