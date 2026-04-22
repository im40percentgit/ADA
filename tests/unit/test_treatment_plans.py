"""
Unit tests for treatment plan CRUD and REST endpoints (Phase 14b, Task 1).

Tests use a real in-memory SQLite database — no mocks of internal modules.
Coverage:
  - StateManager CRUD: create/get/list/update treatment plans, goals, interventions
  - StateManager queries: get_goals_by_metric
  - REST endpoints: full CRUD lifecycle, role gating, validation errors

@decision DEC-TX-TEST-001
@title Treatment plan tests use real in-memory SQLite
@status accepted
@rationale Follows Sacred Practice #5 and the established pattern from
    test_organizations.py. Real in-memory SQLite exercises SQL constraints
    (CHECK, REFERENCES) and query correctness without mocks.
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
# User stubs
# ---------------------------------------------------------------------------

_CLINICIAN_ID = "user-clin-001"
_CLINICIAN_EMAIL = "clinician@example.com"
_ADMIN_ID = "user-admin-001"
_ADMIN_EMAIL = "admin@example.com"
_PATIENT_USER_ID = "user-patient-001"
_PATIENT_USER_EMAIL = "patient@example.com"
_PATIENT_ID = "patient-001"


def _user(uid: str, email: str, role: str = "clinician") -> User:
    return User(
        id=uid,
        email=email,
        role=role,
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


_CLINICIAN_USER = _user(_CLINICIAN_ID, _CLINICIAN_EMAIL, "clinician")
_ADMIN_USER = _user(_ADMIN_ID, _ADMIN_EMAIL, "admin")
_PATIENT_USER = _user(_PATIENT_USER_ID, _PATIENT_USER_EMAIL, "user")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def populated(state: StateManager):
    """StateManager pre-populated with users, a patient, and a treatment plan."""
    for uid, email, role in [
        (_CLINICIAN_ID, _CLINICIAN_EMAIL, "clinician"),
        (_ADMIN_ID, _ADMIN_EMAIL, "admin"),
        (_PATIENT_USER_ID, _PATIENT_USER_EMAIL, "user"),
    ]:
        await state.create_user({
            "id": uid,
            "email": email,
            "hashed_password": "x",
            "role": role,
        })

    await state.create_patient({
        "id": _PATIENT_ID,
        "name": "Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })

    # Add all test users to a care circle so require_patient_access passes.
    await state.create_care_circle("circle-tx-001", _PATIENT_ID)
    for uid in (_CLINICIAN_ID, _ADMIN_ID, _PATIENT_USER_ID):
        await state.add_circle_member(f"ccm-tx-{uid}", "circle-tx-001", uid, "member")

    await state.create_treatment_plan({
        "id": "plan-1",
        "patient_id": _PATIENT_ID,
        "clinician_id": _CLINICIAN_ID,
        "title": "Anxiety Management Plan",
    })

    await state.create_treatment_goal({
        "id": "goal-1",
        "plan_id": "plan-1",
        "description": "Reduce GAD-7 score below 10",
        "target_metric": "gad7",
        "target_operator": "<",
        "target_value": 10.0,
        "current_value": 15.0,
    })

    await state.create_treatment_intervention({
        "id": "interv-1",
        "goal_id": "goal-1",
        "description": "Weekly CBT sessions",
        "frequency": "weekly",
    })

    return state


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@contextmanager
def _client(state: StateManager, user: User) -> Generator[TestClient, None, None]:
    """Authenticated TestClient wired to the given StateManager and user."""
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ===========================================================================
# StateManager CRUD tests
# ===========================================================================


@pytest.mark.asyncio
async def test_create_and_get_treatment_plan(populated: StateManager):
    """Create a plan and retrieve it with nested goals and interventions."""
    plan = await populated.get_treatment_plan("plan-1")
    assert plan is not None
    assert plan["title"] == "Anxiety Management Plan"
    assert plan["status"] == "active"
    assert plan["patient_id"] == _PATIENT_ID
    assert plan["clinician_id"] == _CLINICIAN_ID
    assert len(plan["goals"]) == 1
    assert plan["goals"][0]["description"] == "Reduce GAD-7 score below 10"
    assert len(plan["goals"][0]["interventions"]) == 1
    assert plan["goals"][0]["interventions"][0]["description"] == "Weekly CBT sessions"


@pytest.mark.asyncio
async def test_get_treatment_plan_not_found(state: StateManager):
    """get_treatment_plan returns None for nonexistent ID."""
    result = await state.get_treatment_plan("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_treatment_plans(populated: StateManager):
    """list_treatment_plans returns all plans for a patient."""
    plans = await populated.list_treatment_plans(_PATIENT_ID)
    assert len(plans) == 1
    assert plans[0]["id"] == "plan-1"


@pytest.mark.asyncio
async def test_list_treatment_plans_empty(state: StateManager):
    """list_treatment_plans returns empty list for patient with no plans."""
    result = await state.list_treatment_plans("nonexistent-patient")
    assert result == []


@pytest.mark.asyncio
async def test_update_treatment_plan(populated: StateManager):
    """Update title and status on a plan."""
    await populated.update_treatment_plan("plan-1", {
        "title": "Updated Plan Title",
        "status": "completed",
    })
    plan = await populated.get_treatment_plan("plan-1")
    assert plan["title"] == "Updated Plan Title"
    assert plan["status"] == "completed"
    assert plan["updated_at"] is not None


@pytest.mark.asyncio
async def test_update_treatment_plan_ignores_unknown(populated: StateManager):
    """Unknown fields are silently ignored."""
    await populated.update_treatment_plan("plan-1", {"bogus": "value"})
    plan = await populated.get_treatment_plan("plan-1")
    assert plan["title"] == "Anxiety Management Plan"  # unchanged


@pytest.mark.asyncio
async def test_update_treatment_goal(populated: StateManager):
    """Update fields on a treatment goal."""
    await populated.update_treatment_goal("goal-1", {
        "current_value": 8.0,
        "status": "met",
    })
    plan = await populated.get_treatment_plan("plan-1")
    goal = plan["goals"][0]
    assert goal["current_value"] == 8.0
    assert goal["status"] == "met"


@pytest.mark.asyncio
async def test_get_goals_by_metric(populated: StateManager):
    """get_goals_by_metric returns goals matching the target_metric."""
    goals = await populated.get_goals_by_metric(_PATIENT_ID, "gad7")
    assert len(goals) == 1
    assert goals[0]["id"] == "goal-1"
    assert goals[0]["target_metric"] == "gad7"


@pytest.mark.asyncio
async def test_get_goals_by_metric_empty(populated: StateManager):
    """get_goals_by_metric returns empty list for unmatched metric."""
    goals = await populated.get_goals_by_metric(_PATIENT_ID, "phq9")
    assert goals == []


@pytest.mark.asyncio
async def test_create_and_update_intervention(populated: StateManager):
    """Create a second intervention and update it."""
    await populated.create_treatment_intervention({
        "id": "interv-2",
        "goal_id": "goal-1",
        "description": "Mindfulness exercises",
        "frequency": "daily",
    })

    plan = await populated.get_treatment_plan("plan-1")
    assert len(plan["goals"][0]["interventions"]) == 2

    await populated.update_treatment_intervention("interv-2", {
        "status": "completed",
        "frequency": "as needed",
    })

    # Verify via get_treatment_plan
    plan = await populated.get_treatment_plan("plan-1")
    interv = [i for i in plan["goals"][0]["interventions"] if i["id"] == "interv-2"][0]
    assert interv["status"] == "completed"
    assert interv["frequency"] == "as needed"


@pytest.mark.asyncio
async def test_plan_status_check_constraint(state: StateManager):
    """CHECK constraint rejects invalid plan status values."""
    await state.create_patient({
        "id": "p-check",
        "name": "Check Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await state.create_user({
        "id": "u-check",
        "email": "check@test.com",
        "hashed_password": "x",
        "role": "clinician",
    })
    with pytest.raises(Exception):
        await state.create_treatment_plan({
            "id": "plan-bad",
            "patient_id": "p-check",
            "clinician_id": "u-check",
            "title": "Bad Plan",
            "status": "invalid_status",
        })


@pytest.mark.asyncio
async def test_goal_status_check_constraint(populated: StateManager):
    """CHECK constraint rejects invalid goal status values."""
    with pytest.raises(Exception):
        await populated.create_treatment_goal({
            "id": "goal-bad",
            "plan_id": "plan-1",
            "description": "Bad goal",
            "status": "invalid_status",
        })


@pytest.mark.asyncio
async def test_intervention_status_check_constraint(populated: StateManager):
    """CHECK constraint rejects invalid intervention status values."""
    with pytest.raises(Exception):
        await populated.create_treatment_intervention({
            "id": "interv-bad",
            "goal_id": "goal-1",
            "description": "Bad intervention",
            "status": "invalid_status",
        })


# ===========================================================================
# REST endpoint tests
# ===========================================================================


def test_create_plan_as_clinician(populated):
    """Clinician can create a treatment plan."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.post(
            f"/api/patients/{_PATIENT_ID}/treatment-plans",
            json={"title": "Depression Management"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Depression Management"
    assert body["status"] == "active"
    assert body["patient_id"] == _PATIENT_ID
    assert body["clinician_id"] == _CLINICIAN_ID
    assert "goals" in body


def test_create_plan_as_admin(populated):
    """Admin can create a treatment plan."""
    with _client(populated, _ADMIN_USER) as client:
        resp = client.post(
            f"/api/patients/{_PATIENT_ID}/treatment-plans",
            json={"title": "Admin Created Plan"},
        )
    assert resp.status_code == 201


def test_create_plan_as_patient_forbidden(populated):
    """Patient (user role) cannot create a treatment plan (403)."""
    with _client(populated, _PATIENT_USER) as client:
        resp = client.post(
            f"/api/patients/{_PATIENT_ID}/treatment-plans",
            json={"title": "Not Allowed"},
        )
    assert resp.status_code == 403


def test_create_plan_missing_title(populated):
    """Missing title returns 400."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.post(
            f"/api/patients/{_PATIENT_ID}/treatment-plans",
            json={},
        )
    assert resp.status_code == 400
    assert "title is required" in resp.json()["detail"]


def test_list_plans(populated):
    """List treatment plans for a patient."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.get(f"/api/patients/{_PATIENT_ID}/treatment-plans")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["id"] == "plan-1"


def test_get_plan_detail(populated):
    """Get plan detail with nested goals and interventions."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.get("/api/treatment-plans/plan-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Anxiety Management Plan"
    assert len(body["goals"]) == 1
    assert len(body["goals"][0]["interventions"]) == 1


def test_get_plan_not_found(populated):
    """Nonexistent plan returns 404."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.get("/api/treatment-plans/nonexistent")
    assert resp.status_code == 404


def test_update_plan(populated):
    """Update plan title and status."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.put(
            "/api/treatment-plans/plan-1",
            json={"title": "Updated Title", "status": "completed"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Updated Title"
    assert body["status"] == "completed"


def test_update_plan_invalid_status(populated):
    """Invalid status returns 400."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.put(
            "/api/treatment-plans/plan-1",
            json={"status": "invalid"},
        )
    assert resp.status_code == 400


def test_update_plan_not_found(populated):
    """Updating nonexistent plan returns 404."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.put(
            "/api/treatment-plans/nonexistent",
            json={"title": "Nope"},
        )
    assert resp.status_code == 404


def test_update_plan_patient_forbidden(populated):
    """Patient cannot update a plan (403)."""
    with _client(populated, _PATIENT_USER) as client:
        resp = client.put(
            "/api/treatment-plans/plan-1",
            json={"title": "Nope"},
        )
    assert resp.status_code == 403


def test_create_goal(populated):
    """Clinician can add a goal to a plan."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.post(
            "/api/treatment-plans/plan-1/goals",
            json={
                "description": "Improve WHO-5 score above 50",
                "target_metric": "who5",
                "target_operator": ">",
                "target_value": 50.0,
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] == "Improve WHO-5 score above 50"
    assert body["target_metric"] == "who5"


def test_create_goal_missing_description(populated):
    """Missing description returns 400."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.post(
            "/api/treatment-plans/plan-1/goals",
            json={},
        )
    assert resp.status_code == 400
    assert "description is required" in resp.json()["detail"]


def test_create_goal_plan_not_found(populated):
    """Adding goal to nonexistent plan returns 404."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.post(
            "/api/treatment-plans/nonexistent/goals",
            json={"description": "Nope"},
        )
    assert resp.status_code == 404


def test_update_goal(populated):
    """Update a treatment goal's status and current_value."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.put(
            "/api/treatment-goals/goal-1",
            json={"current_value": 7.0, "status": "met"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_value"] == 7.0
    assert body["status"] == "met"


def test_update_goal_invalid_status(populated):
    """Invalid goal status returns 400."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.put(
            "/api/treatment-goals/goal-1",
            json={"status": "bogus"},
        )
    assert resp.status_code == 400


def test_create_intervention(populated):
    """Clinician can add an intervention to a goal."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.post(
            "/api/treatment-goals/goal-1/interventions",
            json={"description": "Daily journaling", "frequency": "daily"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] == "Daily journaling"
    assert body["frequency"] == "daily"
    assert body["status"] == "active"


def test_create_intervention_missing_description(populated):
    """Missing description returns 400."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.post(
            "/api/treatment-goals/goal-1/interventions",
            json={},
        )
    assert resp.status_code == 400
    assert "description is required" in resp.json()["detail"]


def test_update_intervention(populated):
    """Update an intervention's status."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.put(
            "/api/treatment-interventions/interv-1",
            json={"status": "completed"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"


def test_update_intervention_invalid_status(populated):
    """Invalid intervention status returns 400."""
    with _client(populated, _CLINICIAN_USER) as client:
        resp = client.put(
            "/api/treatment-interventions/interv-1",
            json={"status": "bogus"},
        )
    assert resp.status_code == 400


# ===========================================================================
# Event type verification
# ===========================================================================


def test_treatment_goal_met_event():
    """TreatmentGoalMetEvent can be instantiated with expected fields."""
    from ada.core.events import TreatmentGoalMetEvent, EventTypes

    event = TreatmentGoalMetEvent(
        goal_id="g1",
        plan_id="p1",
        patient_id="pat1",
        description="Reduce anxiety",
        target_metric="gad7",
        target_value=10.0,
        current_value=8.0,
    )
    assert event.event_type == EventTypes.TREATMENT_GOAL_MET
    assert event.goal_id == "g1"
    assert event.target_value == 10.0
    assert event.current_value == 8.0
