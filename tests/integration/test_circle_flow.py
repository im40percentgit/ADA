"""Integration test: full care circle lifecycle.

Exercises the complete care circle flow from migration through member
management using a real in-memory SQLite StateManager and FastAPI TestClient.

Test coverage:
- Auto-migration creates a care circle from legacy caregiver_id data
- Caregiver can list circles they belong to
- Caregiver can add a new family member by email
- Added family member sees the circle immediately
- Both caregiver and family member appear in the members list
- Caregiver overview endpoint still returns correct patient data
- Caregiver can remove a family member
- Removed member no longer sees the circle

@decision DEC-CIRCLE-004
@title Circle integration test uses auto-migration + real HTTP round-trips
@status accepted
@rationale Unit tests cover edge cases for individual state methods and
    route-level auth. This integration test validates the full vertical slice:
    legacy data migration, circle membership CRUD via HTTP, and cross-user
    visibility -- confirming the multi-user care circle design works end-to-end.
"""

from __future__ import annotations

from datetime import datetime

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


def _make_client(state: StateManager, user: User) -> TestClient:
    """Return a TestClient that must be used as a context manager to trigger lifespan."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    # TestClient must be entered as a context manager so lifespan sets app.state.state_manager
    return TestClient(app, raise_server_exceptions=True)


def _user(uid: str, email: str, role: str = "caregiver") -> User:
    return User(id=uid, email=email, role=role, patient_id=None, created_at=datetime.utcnow(), is_active=True)


@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email, role in [
        ("user-cg", "caregiver@test.com", "caregiver"),
        ("user-fam", "family@test.com", "caregiver"),
    ]:
        await sm._exec(
            "INSERT INTO users (id, email, hashed_password, role, created_at, is_active)"
            " VALUES (?, ?, ?, ?, datetime('now'), 1)",
            (uid, email, "hashed", role),
        )

    # Patient with legacy caregiver_id triggers auto-migration
    await sm.create_patient({
        "id": "pat-1",
        "name": "Alice",
        "dob": "1990-01-01",
        "emergency_contact": None,
        "caregiver_id": "user-cg",
    })

    # Run migration manually since patient was created after initialize()
    await sm._migrate_caregiver_to_circles()

    yield sm
    await sm.close()


@pytest.mark.asyncio
async def test_full_circle_lifecycle(state: StateManager):
    """Migration -> list circles -> add member -> overview -> remove member."""
    cg = _user("user-cg", "caregiver@test.com")
    fam = _user("user-fam", "family@test.com")

    # Both clients share the same in-memory StateManager so changes made via
    # client_cg are immediately visible to client_fam (same SQLite connection).
    # Each TestClient must be entered as a context manager to trigger the
    # FastAPI lifespan, which registers app.state.state_manager.
    with _make_client(state, cg) as client_cg, _make_client(state, fam) as client_fam:
        # 1. Migration created a circle
        resp = client_cg.get("/api/circles/my")
        assert resp.status_code == 200
        circles = resp.json()
        assert len(circles) == 1
        assert circles[0]["patient_name"] == "Alice"
        circle_id = circles[0]["id"]

        # 2. Add family member
        resp = client_cg.post(
            f"/api/circles/{circle_id}/members",
            json={"email": "family@test.com", "role": "family"},
        )
        assert resp.status_code == 201

        # 3. Family member sees the circle
        resp = client_fam.get("/api/circles/my")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # 4. Both see members
        resp = client_fam.get(f"/api/circles/{circle_id}/members")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        # 5. Caregiver overview works
        resp = client_cg.get("/api/caregiver/overview")
        assert resp.status_code == 200
        assert resp.json()["patient"]["name"] == "Alice"

        # 6. Remove family member
        resp = client_cg.delete(f"/api/circles/{circle_id}/members/user-fam")
        assert resp.status_code == 204

        # 7. Family member no longer sees circle
        resp = client_fam.get("/api/circles/my")
        assert resp.status_code == 200
        assert len(resp.json()) == 0
