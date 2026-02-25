"""
Tests for media WebSocket endpoint (/ws/media/{session_id}).

Uses Starlette's sync TestClient with sync def test methods -- async test
functions do not work with TestClient's sync WebSocket context manager.

@decision DEC-MULTIMODAL-001
@title Separate /ws/media/ from /ws/chat/
@status accepted
@rationale Media streams (audio at ~100ms chunks, video at ~1fps) generate
    high-frequency data that could block the chat WebSocket's response
    queue. Separate connections allow independent failure and flow control.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from ada.api.app import create_app
from ada.agents.registry import AgentRegistry
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager


@pytest.fixture
async def app_setup():
    config = AdaConfig()
    config.auth.enabled = False
    state = StateManager(":memory:")
    await state.initialize()
    bus = EventBus()
    await bus.start()
    registry = AgentRegistry(bus, config, state, None)
    app = create_app(config, bus, state, registry)
    yield app, bus, state, config
    await bus.stop()
    await state.close()


class TestMediaWebSocket:
    def test_media_route_exists(self, app_setup):
        app, bus, state, config = app_setup
        routes = [r.path for r in app.routes]
        assert "/ws/media/{session_id}" in routes

    def test_sensor_data_accepted(self, app_setup):
        app, bus, state, config = app_setup
        with TestClient(app) as client:
            with client.websocket_connect("/ws/media/test-session") as ws:
                ws.send_json({"type": "auth", "token": "test"})
                ws.send_json({
                    "type": "sensor_data",
                    "sensor_type": "hr",
                    "value": 72.0,
                    "unit": "bpm",
                    "patient_id": "p1",
                })
                response = ws.receive_json()
                assert response["type"] == "ack"

    def test_audio_chunk_accepted(self, app_setup):
        app, bus, state, config = app_setup
        with TestClient(app) as client:
            with client.websocket_connect("/ws/media/test-session") as ws:
                ws.send_json({"type": "auth", "token": "test"})
                ws.send_json({
                    "type": "audio_chunk",
                    "patient_id": "p1",
                    "metadata": {"codec": "webm/opus", "sample_rate": 48000},
                })
                ws.send_bytes(b"\x00" * 1024)
                response = ws.receive_json()
                assert response["type"] == "ack"

    def test_video_frame_accepted(self, app_setup):
        app, bus, state, config = app_setup
        with TestClient(app) as client:
            with client.websocket_connect("/ws/media/test-session") as ws:
                ws.send_json({"type": "auth", "token": "test"})
                ws.send_json({
                    "type": "video_frame",
                    "patient_id": "p1",
                    "metadata": {"resolution": "640x480", "format": "jpeg"},
                })
                ws.send_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
                response = ws.receive_json()
                assert response["type"] == "ack"

    def test_unknown_type_returns_error(self, app_setup):
        app, bus, state, config = app_setup
        with TestClient(app) as client:
            with client.websocket_connect("/ws/media/test-session") as ws:
                ws.send_json({"type": "auth", "token": "test"})
                ws.send_json({"type": "unknown_data", "patient_id": "p1"})
                response = ws.receive_json()
                assert response["type"] == "error"
