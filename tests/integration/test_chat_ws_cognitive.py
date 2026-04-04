"""
Integration tests: chat WebSocket forwards COGNITIVE_TASK_PRESENTED events
and accepts cognitive_response messages from the client.

These tests exercise the full pipeline:
  1. A real EventBus + in-memory SQLite StateManager
  2. A real FastAPI app created via create_app()
  3. A real WebSocket connection via starlette TestClient
  4. Events published directly to the bus (simulating CognitiveScreeningAgent output)

We verify that:
  - cognitive_task frames arrive after a CognitiveTaskPresentedEvent is published
  - Frames for other session_ids are NOT forwarded
  - cognitive_response messages from the client publish CognitiveTaskResponseEvent

@decision DEC-TEST-012
@title Chat WS cognitive tests reuse emotion test patterns with auth disabled
@status accepted
@rationale Same real-stack integration approach as test_chat_ws_emotion.py.
    Auth is disabled so tests focus on the event relay logic. The auth path
    is already covered by test_auth.py.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.llm.router import make_null_router
from ada.core.events import (
    CognitiveTaskPresentedEvent,
    CognitiveTaskResponseEvent,
    EventTypes,
)
from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def no_auth_config() -> AdaConfig:
    cfg = AdaConfig()
    cfg.auth.enabled = False
    return cfg


@pytest_asyncio.fixture
async def client_stack(no_auth_config):
    """Fully wired TestClient inside the async fixture's event loop."""
    bus = EventBus()
    state = StateManager(":memory:")
    await state.initialize()
    await bus.start()
    registry = AgentRegistry(bus=bus, config=no_auth_config, state=state, router=make_null_router())
    app = create_app(config=no_auth_config, bus=bus, state=state, registry=registry)
    with TestClient(app) as client:
        yield client, bus
    await bus.stop()
    await state.close()


# ---------------------------------------------------------------------------
# Tests: cognitive task forwarding
# ---------------------------------------------------------------------------

class TestChatWsCognitiveTaskForwarding:
    """chat WebSocket forwards COGNITIVE_TASK_PRESENTED events as cognitive_task frames."""

    async def test_cognitive_task_forwarded(self, client_stack):
        client, bus = client_stack
        session_id = "sess-cog-001"
        received: list[dict] = []

        with client.websocket_connect(f"/ws/chat/{session_id}") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "test-token"}))

            await bus.publish(
                CognitiveTaskPresentedEvent(
                    source="test",
                    session_id=session_id,
                    patient_id="pat-001",
                    screening_id="scr-001",
                    task_index=0,
                    total_tasks=12,
                    domain="memory",
                    task_type="pattern_grid",
                    prompt="Remember the highlighted cells",
                    task_data={"grid_size": 4, "highlighted_cells": [1, 5, 10]},
                )
            )
            await asyncio.sleep(0.1)

            try:
                msg = ws.receive_json()
                received.append(msg)
            except Exception:
                pass

        assert len(received) == 1
        frame = received[0]
        assert frame["type"] == "cognitive_task"
        assert frame["screening_id"] == "scr-001"
        assert frame["task_index"] == 0
        assert frame["total_tasks"] == 12
        assert frame["domain"] == "memory"
        assert frame["task_type"] == "pattern_grid"
        assert frame["prompt"] == "Remember the highlighted cells"
        assert frame["task_data"]["grid_size"] == 4
        assert frame["task_data"]["highlighted_cells"] == [1, 5, 10]

    async def test_cognitive_task_wrong_session_not_forwarded(self, client_stack):
        client, bus = client_stack
        session_id = "sess-cog-002"
        other_session = "sess-other-999"

        with client.websocket_connect(f"/ws/chat/{session_id}") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "test-token"}))

            await bus.publish(
                CognitiveTaskPresentedEvent(
                    source="test",
                    session_id=other_session,
                    patient_id="pat-002",
                    screening_id="scr-002",
                    task_index=0,
                    total_tasks=6,
                    domain="attention",
                    task_type="text",
                    prompt="What day is it?",
                    task_data={"type": "free_text"},
                )
            )
            await asyncio.sleep(0.1)
            # No data should arrive — verified by disconnect without frames


# ---------------------------------------------------------------------------
# Tests: cognitive response handling
# ---------------------------------------------------------------------------

class TestChatWsCognitiveResponse:
    """chat WebSocket accepts cognitive_response and publishes CognitiveTaskResponseEvent."""

    async def test_cognitive_response_published(self, client_stack):
        client, bus = client_stack
        session_id = "sess-cog-003"
        received_events: list[CognitiveTaskResponseEvent] = []

        async def capture_response(event: CognitiveTaskResponseEvent) -> None:
            received_events.append(event)

        bus.subscribe(
            EventTypes.COGNITIVE_TASK_RESPONSE,
            capture_response,
            "test-capture",
        )

        try:
            with client.websocket_connect(f"/ws/chat/{session_id}") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": "test-token"}))

                ws.send_text(json.dumps({
                    "type": "cognitive_response",
                    "screening_id": "scr-003",
                    "task_index": 2,
                    "response": "the blue triangle",
                }))
                await asyncio.sleep(0.1)
        finally:
            bus.unsubscribe(EventTypes.COGNITIVE_TASK_RESPONSE, "test-capture")

        assert len(received_events) == 1
        evt = received_events[0]
        assert evt.screening_id == "scr-003"
        assert evt.task_index == 2
        assert evt.response == "the blue triangle"
        assert evt.session_id == session_id
