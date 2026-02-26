"""
Unit tests for sensor simulator REST endpoints.

Tests /api/sessions/{session_id}/simulator/start and /stop using a
real FastAPI TestClient with a real EventBus and in-memory SQLite.
No mocks — the simulator itself runs as a real asyncio.Task.

@decision DEC-TEST-008
@title Simulator endpoint tests use short duration to avoid slow test runs
@status accepted
@rationale The simulator generates readings at 1 Hz. Tests use duration_s=1
    to produce exactly one tick then stop naturally, keeping test runtime
    under 3 seconds. The stop endpoint is separately tested with a long
    duration that is cancelled immediately.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes, SensorReadingEvent
from ada.core.state import StateManager


# ---------------------------------------------------------------------------
# Fixtures — async fixture keeps the event loop alive for the full test
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> AdaConfig:
    cfg = AdaConfig()
    cfg.auth.enabled = False
    return cfg


@pytest_asyncio.fixture
async def client_stack(config):
    """Fully wired TestClient inside the async fixture's event loop."""
    bus = EventBus()
    state = StateManager(":memory:")
    await state.initialize()
    await bus.start()
    registry = AgentRegistry(bus=bus, config=config, state=state, llm=None)
    app = create_app(config=config, bus=bus, state=state, registry=registry)
    with TestClient(app) as client:
        yield client, bus
    await bus.stop()
    await state.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSimulatorStart:

    def test_start_returns_202(self, client_stack):
        client, _ = client_stack
        res = client.post(
            "/api/sessions/test-session/simulator/start",
            json={"preset": "relaxed", "duration_s": 1},
        )
        assert res.status_code == 202
        body = res.json()
        assert body["status"] == "started"
        assert body["preset"] == "relaxed"
        assert body["session_id"] == "test-session"
        client.post("/api/sessions/test-session/simulator/stop")

    def test_start_invalid_preset_returns_422(self, client_stack):
        client, _ = client_stack
        res = client.post(
            "/api/sessions/test-session/simulator/start",
            json={"preset": "nonexistent_preset"},
        )
        assert res.status_code == 422

    def test_start_all_valid_presets(self, client_stack):
        client, _ = client_stack
        for preset in ("relaxed", "anxious", "panic_attack"):
            res = client.post(
                f"/api/sessions/sim-{preset}/simulator/start",
                json={"preset": preset, "duration_s": 1},
            )
            assert res.status_code == 202, f"Failed for preset {preset}: {res.text}"
            client.post(f"/api/sessions/sim-{preset}/simulator/stop")

    async def test_start_emits_sensor_reading_events(self, client_stack):
        """A running simulator should emit SENSOR_READING events to the bus."""
        client, bus = client_stack
        readings: list[SensorReadingEvent] = []

        async def capture(event):
            readings.append(event)

        # Subscribe while the event loop is running (inside async test)
        bus.subscribe(EventTypes.SENSOR_READING, capture, "test-capture-emit")

        res = client.post(
            "/api/sessions/emit-test-session/simulator/start",
            json={"preset": "relaxed", "duration_s": 2},
        )
        assert res.status_code == 202

        # Allow at least one full tick (1 second + dispatch time)
        await asyncio.sleep(1.5)

        client.post("/api/sessions/emit-test-session/simulator/stop")
        bus.unsubscribe(EventTypes.SENSOR_READING, "test-capture-emit")

        # Should have at least 3 readings (hr + gsr + spo2 per tick)
        assert len(readings) >= 3
        sensor_types = {r.sensor_type for r in readings}
        assert "hr" in sensor_types
        assert "gsr" in sensor_types
        assert "spo2" in sensor_types


class TestSimulatorStop:

    def test_stop_running_simulator(self, client_stack):
        client, _ = client_stack
        start_res = client.post(
            "/api/sessions/stop-test/simulator/start",
            json={"preset": "anxious", "duration_s": 300},
        )
        assert start_res.status_code == 202

        stop_res = client.post("/api/sessions/stop-test/simulator/stop")
        assert stop_res.status_code == 200
        body = stop_res.json()
        assert body["status"] == "stopped"
        assert body["session_id"] == "stop-test"

    def test_stop_idle_returns_idle(self, client_stack):
        client, _ = client_stack
        res = client.post("/api/sessions/never-started/simulator/stop")
        assert res.status_code == 200
        assert res.json()["status"] == "idle"

    def test_start_conflict_returns_409(self, client_stack):
        """Starting a second simulator for the same session should return 409."""
        client, _ = client_stack
        r1 = client.post(
            "/api/sessions/conflict-session/simulator/start",
            json={"preset": "relaxed", "duration_s": 300},
        )
        assert r1.status_code == 202

        r2 = client.post(
            "/api/sessions/conflict-session/simulator/start",
            json={"preset": "anxious", "duration_s": 300},
        )
        assert r2.status_code == 409

        client.post("/api/sessions/conflict-session/simulator/stop")
