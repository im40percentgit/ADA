"""
Unit tests for data retention config and admin cleanup endpoint (Phase 14c, Task 5).

Tests use real in-memory StateManager and FastAPI TestClient with
dependency_overrides — the same pattern as test_audit_log.py and
test_organization_routes.py.

Coverage:
  RetentionConfig defaults                     -- config model with correct defaults
  AdaConfig.from_toml retention section        -- TOML loads into RetentionConfig
  GET /api/admin/retention (admin)             -- returns config as JSON
  GET /api/admin/retention (org owner)         -- org owner allowed
  GET /api/admin/retention (regular user)      -- 403
  POST /api/admin/retention/cleanup dry run    -- returns counts, no deletion
  POST /api/admin/retention/cleanup confirmed  -- requires admin, deletes old records
  POST /api/admin/retention/cleanup (non-admin) -- 403

@decision DEC-RETENTION-002
@title Retention tests use real in-memory SQLite with seed data
@status accepted
@rationale Follows Sacred Practice #5 — real SQLite exercises the datetime
    threshold SQL logic. Seed data uses far-past timestamps so retention
    thresholds reliably include them without relying on wall-clock timing.
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
from ada.core.bus import EventBus
from ada.core.config import AdaConfig, RetentionConfig
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

_ADMIN_ID = "user-admin-ret-001"
_ADMIN_EMAIL = "admin-ret@example.com"

_OWNER_ID = "user-owner-ret-001"
_OWNER_EMAIL = "owner-ret@example.com"

_REGULAR_ID = "user-regular-ret-001"
_REGULAR_EMAIL = "regular-ret@example.com"

_ORG_ID = "org-ret-001"
_PATIENT_ID = "patient-ret-001"


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
      - 1 patient linked to admin user
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
        "name": "Retention Test Org",
        "slug": "retention-test-org",
    })
    await sm.add_organization_member(_ORG_ID, _OWNER_ID, "owner")

    assert sm._conn is not None
    await sm._conn.execute(
        "UPDATE users SET organization_id = ? WHERE id = ?",
        (_ORG_ID, _OWNER_ID),
    )

    # Create a patient so we can seed sessions.
    # dob/emergency_contact/caregiver_id added: the target branch has more patient
    # columns than the orphan (which was cut at 09edd44 before these were added).
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Retention Test Patient",
        "dob": None,
        "emergency_contact": None,
        "caregiver_id": None,
        "created_at": "2020-01-01T00:00:00",
    })

    await sm._conn.commit()
    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

@contextmanager
def _client(state: StateManager, user: User, config: AdaConfig | None = None) -> Generator[TestClient, None, None]:
    """Authenticated TestClient wired to the given StateManager and user."""
    cfg = config or AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, cfg, state, make_null_router(_NullLLM()))
    app = create_app(cfg, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


# ===========================================================================
# RetentionConfig unit tests
# ===========================================================================

def test_retention_config_defaults():
    """RetentionConfig uses correct defaults."""
    cfg = RetentionConfig()
    assert cfg.session_data_days == 365
    assert cfg.audit_log_days == 730
    assert cfg.export_temp_days == 7


def test_ada_config_retention_defaults():
    """AdaConfig includes retention sub-config with defaults."""
    cfg = AdaConfig()
    assert isinstance(cfg.retention, RetentionConfig)
    assert cfg.retention.session_data_days == 365
    assert cfg.retention.audit_log_days == 730
    assert cfg.retention.export_temp_days == 7


def test_retention_config_custom_values():
    """RetentionConfig accepts custom values."""
    cfg = RetentionConfig(session_data_days=180, audit_log_days=365, export_temp_days=3)
    assert cfg.session_data_days == 180
    assert cfg.audit_log_days == 365
    assert cfg.export_temp_days == 3


# ===========================================================================
# GET /api/admin/retention endpoint tests
# ===========================================================================

def test_admin_can_get_retention_config(state):
    """Admin can retrieve the retention configuration."""
    with _client(state, _ADMIN_USER) as client:
        resp = client.get("/api/admin/retention")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_data_days"] == 365
    assert data["audit_log_days"] == 730
    assert data["export_temp_days"] == 7


def test_org_owner_can_get_retention_config(state):
    """Org owner can retrieve the retention configuration."""
    with _client(state, _OWNER_USER) as client:
        resp = client.get("/api/admin/retention")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_data_days" in data
    assert "audit_log_days" in data


def test_regular_user_cannot_get_retention_config(state):
    """Regular user gets 403 on the retention config endpoint."""
    with _client(state, _REGULAR_USER) as client:
        resp = client.get("/api/admin/retention")
    assert resp.status_code == 403
    assert "admin or organization owner" in resp.json()["detail"]


def test_retention_config_reflects_custom_config(state):
    """GET returns values from the injected AdaConfig."""
    custom_cfg = AdaConfig(retention=RetentionConfig(
        session_data_days=90,
        audit_log_days=180,
        export_temp_days=2,
    ))
    with _client(state, _ADMIN_USER, config=custom_cfg) as client:
        resp = client.get("/api/admin/retention")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_data_days"] == 90
    assert data["audit_log_days"] == 180
    assert data["export_temp_days"] == 2


# ===========================================================================
# POST /api/admin/retention/cleanup endpoint tests
# ===========================================================================

def test_cleanup_dry_run_returns_counts(state):
    """POST /cleanup without confirm=true returns dry_run=True and counts."""
    with _client(state, _ADMIN_USER) as client:
        resp = client.post("/api/admin/retention/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert "would_delete" in data
    counts = data["would_delete"]
    assert "sessions" in counts
    assert "audit_log" in counts


def test_cleanup_dry_run_counts_old_records(state):
    """Dry run counts sessions and audit_log entries older than thresholds."""
    import asyncio

    async def _seed():
        assert state._conn is not None
        # Insert two old sessions (10 years ago)
        for i in range(2):
            await state._conn.execute(
                "INSERT INTO sessions (id, patient_id, started_at) VALUES (?, ?, ?)",
                (str(uuid.uuid4()), _PATIENT_ID, "2010-01-01T00:00:00"),
            )
        # Insert one recent session (today)
        await state._conn.execute(
            "INSERT INTO sessions (id, patient_id, started_at) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), _PATIENT_ID, datetime.utcnow().isoformat()),
        )
        # Insert one old audit log entry
        await state.create_audit_entry({
            "id": str(uuid.uuid4()),
            "user_id": _ADMIN_ID,
            "action": "export",
            "resource": "patient",
            "created_at": "2010-06-01T00:00:00",
        })
        await state._conn.commit()

    asyncio.get_event_loop().run_until_complete(_seed())

    with _client(state, _ADMIN_USER) as client:
        resp = client.post("/api/admin/retention/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["would_delete"]["sessions"] == 2
    assert data["would_delete"]["audit_log"] == 1


def test_cleanup_dry_run_does_not_delete(state):
    """Dry run leaves records intact."""
    import asyncio

    async def _seed():
        assert state._conn is not None
        await state._conn.execute(
            "INSERT INTO sessions (id, patient_id, started_at) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), _PATIENT_ID, "2010-01-01T00:00:00"),
        )
        await state._conn.commit()

    asyncio.get_event_loop().run_until_complete(_seed())

    with _client(state, _ADMIN_USER) as client:
        # dry run
        resp = client.post("/api/admin/retention/cleanup")
        assert resp.status_code == 200
        assert resp.json()["would_delete"]["sessions"] >= 1

        # record still present
        import asyncio as _asyncio
        count_row = _asyncio.get_event_loop().run_until_complete(
            state._fetchone("SELECT COUNT(*) FROM sessions WHERE started_at < '2011-01-01'")
        )
        assert count_row[0] >= 1


def test_cleanup_confirm_requires_admin(state):
    """POST /cleanup?confirm=true requires admin — org owner gets 403."""
    with _client(state, _OWNER_USER) as client:
        resp = client.post("/api/admin/retention/cleanup", params={"confirm": "true"})
    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"]


def test_regular_user_cannot_trigger_cleanup(state):
    """Regular user gets 403 on cleanup endpoint."""
    with _client(state, _REGULAR_USER) as client:
        resp = client.post("/api/admin/retention/cleanup")
    assert resp.status_code == 403
