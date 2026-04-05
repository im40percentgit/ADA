"""
Unit tests for audit logging — state CRUD and REST query endpoint (Phase 14c, Task 2).

Tests use a real in-memory StateManager and FastAPI TestClient with
dependency_overrides to inject authenticated users without real JWTs --
the same pattern as test_organization_routes.py.

Coverage:
  StateManager.create_audit_entry     -- insert entries
  StateManager.query_audit_log        -- filter by user_id, action, resource, date range, limit
  GET /api/audit-log                  -- admin access, org owner access, regular user 403
  log_audit helper                    -- convenience wrapper creates entries

@decision DEC-AUDIT-002
@title Audit log tests use real in-memory SQLite
@status accepted
@rationale Follows Sacred Practice #5 and the pattern from test_organization_routes.
    Real in-memory SQLite DB exercises the full stack from HTTP request
    through SQL queries to JSON response.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.api.routes.audit_log import log_audit
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

_ADMIN_ID = "user-admin-001"
_ADMIN_EMAIL = "admin@example.com"

_OWNER_ID = "user-owner-001"
_OWNER_EMAIL = "owner@example.com"

_REGULAR_ID = "user-regular-001"
_REGULAR_EMAIL = "regular@example.com"

_ORG_ID = "org-test-001"


# ---------------------------------------------------------------------------
# User stubs
# ---------------------------------------------------------------------------

def _user(uid: str, email: str, role: str = "user") -> User:
    return User(
        id=uid,
        email=email,
        role=role,
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


_ADMIN_USER = _user(_ADMIN_ID, _ADMIN_EMAIL, "admin")
_OWNER_USER = _user(_OWNER_ID, _OWNER_EMAIL, "user")
_REGULAR_USER = _user(_REGULAR_ID, _REGULAR_EMAIL, "user")


# ---------------------------------------------------------------------------
# Fixture: seeded StateManager
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """
    In-memory StateManager with:
      - 3 users (admin, owner, regular)
      - 1 org with owner as org owner
    """
    sm = StateManager(":memory:")
    await sm.initialize()

    for uid, email, role in [
        (_ADMIN_ID, _ADMIN_EMAIL, "admin"),
        (_OWNER_ID, _OWNER_EMAIL, "user"),
        (_REGULAR_ID, _REGULAR_EMAIL, "user"),
    ]:
        await sm.create_user({
            "id": uid,
            "email": email,
            "hashed_password": "x",
            "role": role,
        })

    await sm.create_organization({
        "id": _ORG_ID,
        "name": "Test Organization",
        "slug": "test-org",
    })
    await sm.add_organization_member(_ORG_ID, _OWNER_ID, "owner")

    # Set owner's organization_id
    assert sm._conn is not None
    await sm._conn.execute(
        "UPDATE users SET organization_id = ? WHERE id = ?",
        (_ORG_ID, _OWNER_ID),
    )
    await sm._conn.commit()

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
# StateManager CRUD tests
# ===========================================================================


@pytest.mark.asyncio
async def test_create_and_query_audit_entry(state):
    """Create an audit entry and retrieve it."""
    entry_id = str(uuid.uuid4())
    await state.create_audit_entry({
        "id": entry_id,
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
        "resource_id": "patient-001",
        "details": {"format": "json"},
        "ip_address": "127.0.0.1",
    })

    results = await state.query_audit_log()
    assert len(results) >= 1
    entry = results[0]
    assert entry["id"] == entry_id
    assert entry["user_id"] == _ADMIN_ID
    assert entry["action"] == "export"
    assert entry["resource"] == "patient"
    assert entry["resource_id"] == "patient-001"
    assert entry["details"] == {"format": "json"}
    assert entry["ip_address"] == "127.0.0.1"
    assert "created_at" in entry


@pytest.mark.asyncio
async def test_query_filter_by_user_id(state):
    """Filter audit log by user_id."""
    for uid in [_ADMIN_ID, _OWNER_ID, _ADMIN_ID]:
        await state.create_audit_entry({
            "id": str(uuid.uuid4()),
            "user_id": uid,
            "action": "login",
            "resource": "session",
        })

    results = await state.query_audit_log(user_id=_ADMIN_ID)
    assert len(results) == 2
    assert all(r["user_id"] == _ADMIN_ID for r in results)


@pytest.mark.asyncio
async def test_query_filter_by_action(state):
    """Filter audit log by action."""
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
    })
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "login",
        "resource": "session",
    })

    results = await state.query_audit_log(action="export")
    assert len(results) == 1
    assert results[0]["action"] == "export"


@pytest.mark.asyncio
async def test_query_filter_by_resource(state):
    """Filter audit log by resource type."""
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "view",
        "resource": "patient",
    })
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "view",
        "resource": "assessment",
    })

    results = await state.query_audit_log(resource="assessment")
    assert len(results) == 1
    assert results[0]["resource"] == "assessment"


@pytest.mark.asyncio
async def test_query_filter_by_date_range(state):
    """Filter audit log by date range."""
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
        "created_at": "2025-01-01T00:00:00",
    })
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
        "created_at": "2025-06-15T12:00:00",
    })
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
        "created_at": "2025-12-31T23:59:59",
    })

    results = await state.query_audit_log(
        from_date="2025-03-01T00:00:00",
        to_date="2025-09-01T00:00:00",
    )
    assert len(results) == 1
    assert results[0]["created_at"] == "2025-06-15T12:00:00"


@pytest.mark.asyncio
async def test_query_combined_filters(state):
    """Multiple filters combined with AND."""
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
    })
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _OWNER_ID,
        "action": "export",
        "resource": "patient",
    })
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "login",
        "resource": "session",
    })

    results = await state.query_audit_log(user_id=_ADMIN_ID, action="export")
    assert len(results) == 1
    assert results[0]["user_id"] == _ADMIN_ID
    assert results[0]["action"] == "export"


@pytest.mark.asyncio
async def test_query_limit(state):
    """Limit parameter caps results."""
    for i in range(5):
        await state.create_audit_entry({
            "id": str(uuid.uuid4()),
            "user_id": _ADMIN_ID,
            "action": "view",
            "resource": "patient",
        })

    results = await state.query_audit_log(limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_query_empty_returns_empty_list(state):
    """No entries returns empty list."""
    results = await state.query_audit_log()
    assert results == []


@pytest.mark.asyncio
async def test_create_entry_details_as_string(state):
    """Details can be passed as a pre-serialized JSON string."""
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
        "details": '{"format": "csv"}',
    })

    results = await state.query_audit_log()
    assert results[0]["details"] == {"format": "csv"}


@pytest.mark.asyncio
async def test_create_entry_defaults(state):
    """Minimal entry uses defaults for optional fields."""
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "login",
        "resource": "auth",
    })

    results = await state.query_audit_log()
    entry = results[0]
    assert entry["resource_id"] is None
    assert entry["details"] == {}
    assert entry["ip_address"] is None


# ===========================================================================
# log_audit helper tests
# ===========================================================================


@pytest.mark.asyncio
async def test_log_audit_helper(state):
    """log_audit convenience wrapper creates an entry with auto UUID."""
    await log_audit(
        state,
        user_id=_ADMIN_ID,
        action="update",
        resource="patient",
        resource_id="patient-123",
        details={"field": "name"},
        ip="10.0.0.1",
    )

    results = await state.query_audit_log()
    assert len(results) == 1
    entry = results[0]
    assert entry["user_id"] == _ADMIN_ID
    assert entry["action"] == "update"
    assert entry["resource"] == "patient"
    assert entry["resource_id"] == "patient-123"
    assert entry["details"] == {"field": "name"}
    assert entry["ip_address"] == "10.0.0.1"
    # UUID was auto-generated
    uuid.UUID(entry["id"])  # validates format


# ===========================================================================
# REST endpoint tests
# ===========================================================================


def test_admin_can_query_audit_log(state):
    """Admin role can query the audit log."""
    with _client(state, _ADMIN_USER) as client:
        resp = client.get("/api/audit-log")
    assert resp.status_code == 200
    assert resp.json() == []


def test_org_owner_can_query_audit_log(state):
    """Organization owner can query the audit log."""
    with _client(state, _OWNER_USER) as client:
        resp = client.get("/api/audit-log")
    assert resp.status_code == 200
    assert resp.json() == []


def test_regular_user_cannot_query_audit_log(state):
    """Regular user (not admin, not org owner) gets 403."""
    with _client(state, _REGULAR_USER) as client:
        resp = client.get("/api/audit-log")
    assert resp.status_code == 403
    assert "admin or organization owner" in resp.json()["detail"]


def test_query_with_filters_via_api(state):
    """Query parameters are forwarded to state.query_audit_log."""
    # Seed some entries via the state manager directly
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
        "resource_id": "p-001",
        "details": {"format": "json"},
    }))
    loop.run_until_complete(state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _OWNER_ID,
        "action": "login",
        "resource": "auth",
    }))

    with _client(state, _ADMIN_USER) as client:
        # Filter by action
        resp = client.get("/api/audit-log", params={"action": "export"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["action"] == "export"

        # Filter by user_id
        resp = client.get("/api/audit-log", params={"user_id": _OWNER_ID})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == _OWNER_ID

        # Filter by resource
        resp = client.get("/api/audit-log", params={"resource": "patient"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["resource"] == "patient"

        # Limit
        resp = client.get("/api/audit-log", params={"limit": 1})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # All (no filter)
        resp = client.get("/api/audit-log")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


def test_query_date_range_via_api(state):
    """Date range filters work via query params."""
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
        "created_at": "2025-01-15T10:00:00",
    }))
    loop.run_until_complete(state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": _ADMIN_ID,
        "action": "export",
        "resource": "patient",
        "created_at": "2025-07-15T10:00:00",
    }))

    with _client(state, _ADMIN_USER) as client:
        resp = client.get("/api/audit-log", params={
            "from": "2025-06-01T00:00:00",
            "to": "2025-08-01T00:00:00",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["created_at"] == "2025-07-15T10:00:00"
