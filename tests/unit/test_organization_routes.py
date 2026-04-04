"""
Unit tests for organization management REST endpoints (Phase 14a, Task 3).

Tests use a real in-memory StateManager and FastAPI TestClient with
dependency_overrides to inject authenticated users without real JWTs --
the same pattern as test_board_routes.py and test_circle_routes.py.

Coverage:
  POST   /api/organizations                     -- create org; slug uniqueness
  GET    /api/organizations/{id}                -- get org; membership required
  PUT    /api/organizations/{id}                -- update org; admin/owner only
  GET    /api/organizations/{id}/members        -- list members; membership required
  POST   /api/organizations/{id}/invite         -- invite user; admin/owner only; 404 for unknown email
  PUT    /api/organizations/{id}/members/{uid}  -- update role; owner only
  DELETE /api/organizations/{id}/members/{uid}  -- remove member; sole owner protection

@decision DEC-ORG-API-002
@title Organization route tests use real in-memory SQLite
@status accepted
@rationale Follows Sacred Practice #5 and the pattern from test_board_routes.
    Real in-memory SQLite DB exercises the full stack from HTTP request
    through SQL queries to JSON response.
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
# Fixed IDs
# ---------------------------------------------------------------------------

_OWNER_ID = "user-owner-001"
_OWNER_EMAIL = "owner@example.com"

_ADMIN_ID = "user-admin-001"
_ADMIN_EMAIL = "admin@example.com"

_MEMBER_ID = "user-member-001"
_MEMBER_EMAIL = "member@example.com"

_OUTSIDER_ID = "user-outsider-001"
_OUTSIDER_EMAIL = "outsider@example.com"

_INVITEE_ID = "user-invitee-001"
_INVITEE_EMAIL = "invitee@example.com"

_ORG_ID = "org-test-001"
_ORG_SLUG = "test-org"


# ---------------------------------------------------------------------------
# User stubs
# ---------------------------------------------------------------------------

def _user(uid: str, email: str, role: str = "admin") -> User:
    return User(
        id=uid,
        email=email,
        role=role,
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


_OWNER_USER = _user(_OWNER_ID, _OWNER_EMAIL)
_ADMIN_USER = _user(_ADMIN_ID, _ADMIN_EMAIL)
_MEMBER_USER = _user(_MEMBER_ID, _MEMBER_EMAIL)
_OUTSIDER_USER = _user(_OUTSIDER_ID, _OUTSIDER_EMAIL)


# ---------------------------------------------------------------------------
# Fixture: seeded StateManager
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """
    In-memory StateManager with:
      - 5 users (owner, admin, member, outsider, invitee)
      - 1 org with 3 members (owner, admin, member)
    """
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email in [
        (_OWNER_ID, _OWNER_EMAIL),
        (_ADMIN_ID, _ADMIN_EMAIL),
        (_MEMBER_ID, _MEMBER_EMAIL),
        (_OUTSIDER_ID, _OUTSIDER_EMAIL),
        (_INVITEE_ID, _INVITEE_EMAIL),
    ]:
        await sm.create_user({
            "id": uid,
            "email": email,
            "hashed_password": "x",
            "role": "admin",
        })

    await sm.create_organization({
        "id": _ORG_ID,
        "name": "Test Organization",
        "slug": _ORG_SLUG,
        "settings": {"theme": "light"},
    })

    await sm.add_organization_member(_ORG_ID, _OWNER_ID, "owner")
    await sm.add_organization_member(_ORG_ID, _ADMIN_ID, "admin")
    await sm.add_organization_member(_ORG_ID, _MEMBER_ID, "member")

    yield sm
    await sm.close()


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
# POST /api/organizations — create org
# ===========================================================================


def test_create_organization(state):
    """Create a new organization — creator becomes owner."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.post(
            "/api/organizations",
            json={"name": "New Org", "slug": "new-org"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "New Org"
    assert body["slug"] == "new-org"
    assert body["plan"] == "free"
    assert "id" in body


def test_create_organization_slug_uniqueness(state):
    """Creating an org with a duplicate slug returns 409."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.post(
            "/api/organizations",
            json={"name": "Duplicate", "slug": _ORG_SLUG},
        )
    assert resp.status_code == 409
    assert "slug already exists" in resp.json()["detail"]


def test_create_organization_missing_name(state):
    """Missing name returns 400."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.post(
            "/api/organizations",
            json={"slug": "no-name"},
        )
    assert resp.status_code == 400
    assert "name is required" in resp.json()["detail"]


def test_create_organization_missing_slug(state):
    """Missing slug returns 400."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.post(
            "/api/organizations",
            json={"name": "No Slug"},
        )
    assert resp.status_code == 400
    assert "slug is required" in resp.json()["detail"]


# ===========================================================================
# GET /api/organizations/{id} — get org details
# ===========================================================================


def test_get_organization(state):
    """Member can retrieve org details including member_count."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.get(f"/api/organizations/{_ORG_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test Organization"
    assert body["member_count"] == 3
    assert body["settings"] == {"theme": "light"}


def test_get_organization_non_member(state):
    """Non-member gets 404."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.get(f"/api/organizations/{_ORG_ID}")
    assert resp.status_code == 404


def test_get_organization_not_found(state):
    """Nonexistent org returns 404."""
    with _client(state, _OWNER_USER) as client:
        resp = client.get("/api/organizations/nonexistent")
    assert resp.status_code == 404


# ===========================================================================
# PUT /api/organizations/{id} — update org
# ===========================================================================


def test_update_organization_owner(state):
    """Owner can update org name and settings."""
    with _client(state, _OWNER_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}",
            json={"name": "Updated Org", "settings": {"theme": "dark"}},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated Org"
    assert body["settings"] == {"theme": "dark"}


def test_update_organization_admin(state):
    """Admin can update org."""
    with _client(state, _ADMIN_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}",
            json={"name": "Admin Updated"},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Admin Updated"


def test_update_organization_member_forbidden(state):
    """Regular member cannot update org (403)."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}",
            json={"name": "Nope"},
        )
    assert resp.status_code == 403


def test_update_organization_outsider(state):
    """Non-member cannot update org (404 — no membership)."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}",
            json={"name": "Nope"},
        )
    assert resp.status_code == 404


# ===========================================================================
# GET /api/organizations/{id}/members — list members
# ===========================================================================


def test_list_members(state):
    """Member can list all members."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.get(f"/api/organizations/{_ORG_ID}/members")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    emails = {m["email"] for m in data}
    assert _OWNER_EMAIL in emails
    assert _ADMIN_EMAIL in emails
    assert _MEMBER_EMAIL in emails


def test_list_members_non_member(state):
    """Non-member gets 404."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.get(f"/api/organizations/{_ORG_ID}/members")
    assert resp.status_code == 404


# ===========================================================================
# POST /api/organizations/{id}/invite — invite existing user
# ===========================================================================


def test_invite_member(state):
    """Admin/owner can invite an existing user by email."""
    with _client(state, _OWNER_USER) as client:
        resp = client.post(
            f"/api/organizations/{_ORG_ID}/invite",
            json={"email": _INVITEE_EMAIL, "role": "member"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == _INVITEE_EMAIL
    assert body["role"] == "member"
    assert body["organization_id"] == _ORG_ID


def test_invite_admin_can_invite(state):
    """Admin can also invite."""
    with _client(state, _ADMIN_USER) as client:
        resp = client.post(
            f"/api/organizations/{_ORG_ID}/invite",
            json={"email": _INVITEE_EMAIL},
        )
    assert resp.status_code == 201


def test_invite_member_role_forbidden(state):
    """Regular member cannot invite (403)."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.post(
            f"/api/organizations/{_ORG_ID}/invite",
            json={"email": _INVITEE_EMAIL},
        )
    assert resp.status_code == 403


def test_invite_user_not_found(state):
    """Inviting a non-existent email returns 404."""
    with _client(state, _OWNER_USER) as client:
        resp = client.post(
            f"/api/organizations/{_ORG_ID}/invite",
            json={"email": "nobody@example.com"},
        )
    assert resp.status_code == 404
    assert "User not found" in resp.json()["detail"]


def test_invite_already_member(state):
    """Inviting a user who is already a member returns 409."""
    with _client(state, _OWNER_USER) as client:
        resp = client.post(
            f"/api/organizations/{_ORG_ID}/invite",
            json={"email": _MEMBER_EMAIL},
        )
    assert resp.status_code == 409
    assert "already a member" in resp.json()["detail"]


def test_invite_missing_email(state):
    """Missing email returns 400."""
    with _client(state, _OWNER_USER) as client:
        resp = client.post(
            f"/api/organizations/{_ORG_ID}/invite",
            json={},
        )
    assert resp.status_code == 400
    assert "email is required" in resp.json()["detail"]


def test_invite_invalid_role(state):
    """Invalid role returns 400."""
    with _client(state, _OWNER_USER) as client:
        resp = client.post(
            f"/api/organizations/{_ORG_ID}/invite",
            json={"email": _INVITEE_EMAIL, "role": "superadmin"},
        )
    assert resp.status_code == 400


# ===========================================================================
# PUT /api/organizations/{id}/members/{uid} — update member role
# ===========================================================================


def test_update_member_role(state):
    """Owner can update a member's role."""
    with _client(state, _OWNER_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}/members/{_MEMBER_ID}",
            json={"role": "admin"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["user_id"] == _MEMBER_ID


def test_update_member_role_admin_forbidden(state):
    """Admin cannot update roles (only owner can)."""
    with _client(state, _ADMIN_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}/members/{_MEMBER_ID}",
            json={"role": "admin"},
        )
    assert resp.status_code == 403


def test_update_member_role_member_forbidden(state):
    """Regular member cannot update roles."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}/members/{_MEMBER_ID}",
            json={"role": "admin"},
        )
    assert resp.status_code == 403


def test_update_member_role_outsider(state):
    """Outsider cannot update roles (404 — no membership)."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}/members/{_MEMBER_ID}",
            json={"role": "admin"},
        )
    assert resp.status_code == 404


def test_update_member_role_invalid(state):
    """Invalid role returns 400."""
    with _client(state, _OWNER_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}/members/{_MEMBER_ID}",
            json={"role": "superadmin"},
        )
    assert resp.status_code == 400


def test_update_nonexistent_member_role(state):
    """Updating role of a non-member returns 404."""
    with _client(state, _OWNER_USER) as client:
        resp = client.put(
            f"/api/organizations/{_ORG_ID}/members/{_OUTSIDER_ID}",
            json={"role": "admin"},
        )
    assert resp.status_code == 404


# ===========================================================================
# DELETE /api/organizations/{id}/members/{uid} — remove member
# ===========================================================================


def test_remove_member(state):
    """Owner can remove a member."""
    with _client(state, _OWNER_USER) as client:
        resp = client.delete(
            f"/api/organizations/{_ORG_ID}/members/{_MEMBER_ID}",
        )
    assert resp.status_code == 204


def test_remove_member_admin_can_remove(state):
    """Admin can also remove a member."""
    with _client(state, _ADMIN_USER) as client:
        resp = client.delete(
            f"/api/organizations/{_ORG_ID}/members/{_MEMBER_ID}",
        )
    assert resp.status_code == 204


def test_remove_member_member_forbidden(state):
    """Regular member cannot remove others (403)."""
    with _client(state, _MEMBER_USER) as client:
        resp = client.delete(
            f"/api/organizations/{_ORG_ID}/members/{_ADMIN_ID}",
        )
    assert resp.status_code == 403


def test_remove_sole_owner(state):
    """Cannot remove the sole owner — returns 400."""
    with _client(state, _OWNER_USER) as client:
        resp = client.delete(
            f"/api/organizations/{_ORG_ID}/members/{_OWNER_ID}",
        )
    assert resp.status_code == 400
    assert "sole owner" in resp.json()["detail"]


def test_remove_nonexistent_member(state):
    """Removing a non-member returns 404."""
    with _client(state, _OWNER_USER) as client:
        resp = client.delete(
            f"/api/organizations/{_ORG_ID}/members/{_OUTSIDER_ID}",
        )
    assert resp.status_code == 404


def test_remove_outsider_forbidden(state):
    """Non-member cannot remove anyone (404 — no membership)."""
    with _client(state, _OUTSIDER_USER) as client:
        resp = client.delete(
            f"/api/organizations/{_ORG_ID}/members/{_MEMBER_ID}",
        )
    assert resp.status_code == 404
