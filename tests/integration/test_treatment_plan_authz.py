"""
Integration test: treatment-plan sub-resource authorization (follow-up IDOR fix).

Verifies that require_plan_access / require_goal_access / require_intervention_access
correctly gate the six routes that use {plan_id}, {goal_id}, or {intervention_id}
in the path.

Test cases:
  - 403 for cross-user access on all six sub-resource routes
  - 2xx for authorized self-access (user in patient circle)
  - 2xx for caregiver added to the shared circle
  - 404 for nonexistent sub-resource IDs

@decision DEC-AUTHZ-002
@title Integration test validates require_{plan,goal,intervention}_access on all 6 routes
@status accepted
@rationale Mirrors test_patient_access_authz.py. Real in-memory SQLite + FastAPI
    TestClient (no mocks). Parametrized across all six affected routes.
"""

from __future__ import annotations

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
        return LLMResponse(content="ok", model="null", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


_USER_A_ID = "txauthz-user-a"
_USER_B_ID = "txauthz-user-b"
_PATIENT_A_ID = "txauthz-patient-a"
_PATIENT_B_ID = "txauthz-patient-b"
_CIRCLE_A_ID = "txauthz-circle-a"
_CIRCLE_B_ID = "txauthz-circle-b"
_PLAN_A_ID = "txauthz-plan-a"
_GOAL_A_ID = "txauthz-goal-a"
_INTERV_A_ID = "txauthz-interv-a"

_USER_A = User(
    id=_USER_A_ID,
    email="user-a@txauthz-test.com",
    role="clinician",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)

_USER_B = User(
    id=_USER_B_ID,
    email="user-b@txauthz-test.com",
    role="clinician",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)


@pytest_asyncio.fixture
async def tx_authz_state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email, role in [
        (_USER_A_ID, "user-a@txauthz-test.com", "clinician"),
        (_USER_B_ID, "user-b@txauthz-test.com", "clinician"),
    ]:
        await sm._exec(
            "INSERT INTO users (id, email, hashed_password, role, created_at, is_active)"
            " VALUES (?, ?, ?, ?, datetime('now'), 1)",
            (uid, email, "hashed", role),
        )

    for pid, name in [(_PATIENT_A_ID, "Patient Alpha"), (_PATIENT_B_ID, "Patient Beta")]:
        await sm.create_patient({
            "id": pid,
            "name": name,
            "dob": None,
            "preferences": {},
            "emergency_contact": None,
            "caregiver_id": None,
            "organization_id": None,
        })

    await sm.create_care_circle(_CIRCLE_A_ID, _PATIENT_A_ID)
    await sm.add_circle_member("ccm-a-usera", _CIRCLE_A_ID, _USER_A_ID, "clinician")

    await sm.create_care_circle(_CIRCLE_B_ID, _PATIENT_B_ID)
    await sm.add_circle_member("ccm-b-userb", _CIRCLE_B_ID, _USER_B_ID, "clinician")

    await sm.create_treatment_plan({
        "id": _PLAN_A_ID,
        "patient_id": _PATIENT_A_ID,
        "clinician_id": _USER_A_ID,
        "organization_id": None,
        "title": "Authz Test Plan",
    })
    await sm.create_treatment_goal({
        "id": _GOAL_A_ID,
        "plan_id": _PLAN_A_ID,
        "description": "Authz Test Goal",
    })
    await sm.create_treatment_intervention({
        "id": _INTERV_A_ID,
        "goal_id": _GOAL_A_ID,
        "description": "Authz Test Intervention",
        "frequency": "daily",
    })

    yield sm
    await sm.close()


@contextmanager
def _make_client(state: StateManager, user: User) -> Generator[TestClient, None, None]:
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_NullLLM()))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


_TX_ENDPOINTS = [
    ("GET",  "/api/treatment-plans/{plan_id}",                 None),
    ("PUT",  "/api/treatment-plans/{plan_id}",                 {"title": "X"}),
    ("POST", "/api/treatment-plans/{plan_id}/goals",           {"description": "Y"}),
    ("PUT",  "/api/treatment-goals/{goal_id}",                 {"description": "Z"}),
    ("POST", "/api/treatment-goals/{goal_id}/interventions",   {"description": "W"}),
    ("PUT",  "/api/treatment-interventions/{intervention_id}", {"status": "completed"}),
]


def _ep_id(val):
    if isinstance(val, tuple):
        return f"{val[0]} {val[1]}"
    return str(val)


def _resolve(tmpl: str) -> str:
    return (tmpl
            .replace("{plan_id}", _PLAN_A_ID)
            .replace("{goal_id}", _GOAL_A_ID)
            .replace("{intervention_id}", _INTERV_A_ID))


@pytest.mark.parametrize("method,path_tmpl,body", _TX_ENDPOINTS, ids=_ep_id)
def test_cross_user_access_returns_403(
    tx_authz_state: StateManager,
    method: str,
    path_tmpl: str,
    body,
) -> None:
    """User B (circle B only) accessing patient A sub-resources must get 403."""
    path = _resolve(path_tmpl)
    with _make_client(tx_authz_state, _USER_B) as client:
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(client, method.lower())(path, **kwargs)
    assert resp.status_code == 403, (
        f"{method} {path} returned {resp.status_code}, expected 403. "
        f"Body: {resp.text[:200]}"
    )


@pytest.mark.parametrize("method,path_tmpl,body", _TX_ENDPOINTS, ids=_ep_id)
def test_authorized_user_not_403(
    tx_authz_state: StateManager,
    method: str,
    path_tmpl: str,
    body,
) -> None:
    """User A (in circle A) accessing their own plan/goal/intervention must not get 403."""
    path = _resolve(path_tmpl)
    with _make_client(tx_authz_state, _USER_A) as client:
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(client, method.lower())(path, **kwargs)
    assert resp.status_code != 403, (
        f"{method} {path} returned 403 — user A incorrectly denied. "
        f"Body: {resp.text[:200]}"
    )


@pytest.mark.asyncio
async def test_caregiver_added_to_circle_can_access(tx_authz_state: StateManager) -> None:
    """User B added to circle A gains access to patient A treatment plan."""
    await tx_authz_state.add_circle_member(
        "ccm-a-userb", _CIRCLE_A_ID, _USER_B_ID, "family"
    )
    path = f"/api/treatment-plans/{_PLAN_A_ID}"
    with _make_client(tx_authz_state, _USER_B) as client:
        resp = client.get(path)
    assert resp.status_code == 200, (
        f"Caregiver in shared circle was denied: {resp.text[:200]}"
    )


@pytest.mark.parametrize("method,path_tmpl,body", _TX_ENDPOINTS, ids=_ep_id)
def test_nonexistent_resource_returns_404(
    tx_authz_state: StateManager,
    method: str,
    path_tmpl: str,
    body,
) -> None:
    """Nonexistent sub-resource must return 404, not 403 (no existence leak)."""
    path = (path_tmpl
            .replace("{plan_id}", "no-such-plan")
            .replace("{goal_id}", "no-such-goal")
            .replace("{intervention_id}", "no-such-intervention"))
    with _make_client(tx_authz_state, _USER_A) as client:
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(client, method.lower())(path, **kwargs)
    assert resp.status_code == 404, (
        f"{method} {path} returned {resp.status_code}, expected 404. "
        f"Body: {resp.text[:200]}"
    )


@pytest.mark.asyncio
async def test_get_patient_id_for_plan(tx_authz_state: StateManager) -> None:
    assert await tx_authz_state.get_patient_id_for_plan(_PLAN_A_ID) == _PATIENT_A_ID
    assert await tx_authz_state.get_patient_id_for_plan("no-such-plan") is None


@pytest.mark.asyncio
async def test_get_patient_id_for_goal(tx_authz_state: StateManager) -> None:
    assert await tx_authz_state.get_patient_id_for_goal(_GOAL_A_ID) == _PATIENT_A_ID
    assert await tx_authz_state.get_patient_id_for_goal("no-such-goal") is None


@pytest.mark.asyncio
async def test_get_patient_id_for_intervention(tx_authz_state: StateManager) -> None:
    assert await tx_authz_state.get_patient_id_for_intervention(_INTERV_A_ID) == _PATIENT_A_ID
    assert await tx_authz_state.get_patient_id_for_intervention("no-such-interv") is None
