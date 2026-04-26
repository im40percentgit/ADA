"""Authorization tests for session-scoped API routes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import create_access_token, hash_password
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.router import make_null_router


@pytest.fixture
async def client_stack():
    config = AdaConfig()
    state = StateManager(":memory:")
    await state.initialize()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router())
    app = create_app(config, bus, state, registry)

    now = datetime.now(tz=UTC).isoformat()
    await state.create_patient({
        "id": "patient-a",
        "name": "Patient A",
        "dob": None,
        "preferences": "{}",
        "emergency_contact": None,
        "caregiver_id": None,
        "created_at": now,
    })
    await state.create_patient({
        "id": "patient-b",
        "name": "Patient B",
        "dob": None,
        "preferences": "{}",
        "emergency_contact": None,
        "caregiver_id": None,
        "created_at": now,
    })
    await state.create_user({
        "id": "user-a",
        "email": "a@example.com",
        "hashed_password": hash_password("password-123"),
        "role": "user",
        "patient_id": "patient-a",
        "created_at": now,
        "is_active": 1,
    })
    await state.create_user({
        "id": "user-b",
        "email": "b@example.com",
        "hashed_password": hash_password("password-123"),
        "role": "user",
        "patient_id": "patient-b",
        "created_at": now,
        "is_active": 1,
    })
    await state.create_session({"id": "session-a", "patient_id": "patient-a"})
    await state.save_message({
        "id": "message-a",
        "session_id": "session-a",
        "role": "user",
        "content": "private note",
        "timestamp": now,
    })

    with TestClient(app) as client:
        yield client, config
    await state.close()


def _auth_headers(config: AdaConfig, user_id: str) -> dict[str, str]:
    token = create_access_token(
        user_id=user_id,
        role="user",
        secret=config.auth.secret_key,
        algorithm=config.auth.algorithm,
        expire_minutes=config.auth.access_token_expire_minutes,
    )
    return {"Authorization": f"Bearer {token}"}


class TestSessionAuthorization:
    def test_session_read_requires_authentication(self, client_stack):
        client, _config = client_stack
        response = client.get("/api/sessions/session-a/messages")
        assert response.status_code == 401

    def test_session_owner_can_read_messages(self, client_stack):
        client, config = client_stack
        response = client.get(
            "/api/sessions/session-a/messages",
            headers=_auth_headers(config, "user-a"),
        )
        assert response.status_code == 200
        assert response.json()[0]["content"] == "private note"

    def test_other_patient_cannot_read_session_messages(self, client_stack):
        client, config = client_stack
        response = client.get(
            "/api/sessions/session-a/messages",
            headers=_auth_headers(config, "user-b"),
        )
        assert response.status_code == 403

    def test_other_patient_cannot_stop_session(self, client_stack):
        client, config = client_stack
        response = client.post(
            "/api/sessions/session-a/end",
            json={"summary": "tampered", "mood_end": 1},
            headers=_auth_headers(config, "user-b"),
        )
        assert response.status_code == 403
