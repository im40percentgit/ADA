"""
Unit tests for crisis alert management endpoints.

Tests use real in-memory SQLite, real FastAPI TestClient (context manager to
trigger lifespan), and dependency_overrides to bypass JWT auth.

Coverage:
- PATCH /api/alerts/{alert_id} -- acknowledge, verify status change
- PATCH /api/alerts/{alert_id} -- resolve, verify resolved_at is set
- PATCH /api/alerts/{alert_id} -- invalid status returns 400
- PATCH /api/alerts/{alert_id} -- missing alert returns 404

@decision DEC-ALERT-001
@title Alert route tests follow established dependency_overrides pattern
@status accepted
@rationale Consistent with test_appointment_routes.py and test_medication_routes.py.
    Auth is tested in test_auth.py; route tests focus on CRUD logic.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User


class _NullLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


_FAKE_USER = User(
    id="user-alert-001",
    email="caregiver@example.com",
    role="caregiver",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)


@contextmanager
def _make_client(state: StateManager) -> Generator[TestClient, None, None]:
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "pat-alert-001",
        "name": "Alert Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


async def _insert_alert(state: StateManager, alert_id: str) -> None:
    """Insert a minimal crisis alert row directly."""
    await state._exec(
        """INSERT INTO crisis_alerts
           (id, patient_id, session_id, severity, trigger_text,
            detection_method, escalation_action, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (alert_id, "pat-alert-001", None, "HIGH", "I want to hurt myself",
         "keyword", None, datetime.utcnow().isoformat()),
    )


class TestAcknowledgeAlert:

    def test_acknowledge_alert(self, state):
        alert_id = str(uuid.uuid4())
        asyncio.get_event_loop().run_until_complete(_insert_alert(state, alert_id))

        with _make_client(state) as client:
            resp = client.patch(
                f"/api/alerts/{alert_id}",
                json={"status": "acknowledged"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "acknowledged"
        assert data.get("resolved_at") is None
        assert data.get("resolved_by") is None


class TestResolveAlert:

    def test_resolve_alert(self, state):
        alert_id = str(uuid.uuid4())
        asyncio.get_event_loop().run_until_complete(_insert_alert(state, alert_id))

        with _make_client(state) as client:
            resp = client.patch(
                f"/api/alerts/{alert_id}",
                json={"status": "resolved"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resolved"
        assert data["resolved_at"] is not None
        assert data["resolved_by"] == _FAKE_USER.id

    def test_resolve_sets_parseable_timestamp(self, state):
        alert_id = str(uuid.uuid4())
        asyncio.get_event_loop().run_until_complete(_insert_alert(state, alert_id))

        with _make_client(state) as client:
            resp = client.patch(
                f"/api/alerts/{alert_id}",
                json={"status": "resolved"},
            )

        resolved_at = resp.json()["resolved_at"]
        assert resolved_at is not None
        # Must be a parseable ISO timestamp
        datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))


class TestInvalidAlertStatus:

    def test_invalid_status_400(self, state):
        alert_id = str(uuid.uuid4())

        with _make_client(state) as client:
            resp = client.patch(
                f"/api/alerts/{alert_id}",
                json={"status": "deleted"},
            )

        assert resp.status_code == 400

    def test_invalid_status_detail_message(self, state):
        with _make_client(state) as client:
            resp = client.patch(
                "/api/alerts/any-id",
                json={"status": "banana"},
            )

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "acknowledged" in detail or "resolved" in detail

    def test_missing_alert_404(self, state):
        with _make_client(state) as client:
            resp = client.patch(
                "/api/alerts/nonexistent-alert-id",
                json={"status": "acknowledged"},
            )

        assert resp.status_code == 404
