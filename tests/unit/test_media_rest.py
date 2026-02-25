"""
Tests for media REST fallback endpoints.

REST fallback allows non-WebSocket clients (mobile, low-bandwidth) to
submit sensor readings, audio chunks, and video frames via HTTP.

@decision DEC-MULTIMODAL-005
@title REST fallback for audio/video/sensor ingest (multipart/form-data)
@status accepted
@rationale WebSocket is preferred for real-time streaming but REST fallback
    ensures mobile clients and low-bandwidth environments can still submit
    data. Multipart form-data is the standard for binary file uploads.
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
async def client_setup():
    config = AdaConfig()
    config.auth.enabled = False
    state = StateManager(":memory:")
    await state.initialize()
    bus = EventBus()
    await bus.start()
    registry = AgentRegistry(bus, config, state, None)
    app = create_app(config, bus, state, registry)
    # Use context-manager form so app lifespan fires and sets app.state.*
    with TestClient(app) as client:
        yield client, bus, state
    await bus.stop()
    await state.close()


class TestSensorEndpoint:
    def test_post_sensor_reading(self, client_setup):
        client, bus, state = client_setup
        response = client.post(
            "/api/sessions/s1/sensor",
            json={
                "sensor_type": "hr",
                "value": 72.0,
                "unit": "bpm",
                "patient_id": "p1",
            },
        )
        assert response.status_code == 201
        assert response.json()["sensor_type"] == "hr"

    def test_post_sensor_invalid_type(self, client_setup):
        client, bus, state = client_setup
        response = client.post(
            "/api/sessions/s1/sensor",
            json={
                "sensor_type": "invalid",
                "value": 1.0,
                "unit": "x",
                "patient_id": "p1",
            },
        )
        assert response.status_code == 422


class TestAudioEndpoint:
    def test_post_audio_chunk(self, client_setup):
        client, bus, state = client_setup
        response = client.post(
            "/api/sessions/s1/audio",
            files={"file": ("chunk.webm", b"\x00" * 1024, "audio/webm")},
            data={"patient_id": "p1"},
        )
        assert response.status_code == 201
        assert "chunk_id" in response.json()


class TestVideoFrameEndpoint:
    def test_post_video_frame(self, client_setup):
        client, bus, state = client_setup
        response = client.post(
            "/api/sessions/s1/video-frame",
            files={"file": ("frame.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, "image/jpeg")},
            data={"patient_id": "p1"},
        )
        assert response.status_code == 201
        assert "frame_id" in response.json()
