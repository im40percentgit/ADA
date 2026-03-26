"""
Unit tests for resolve_circle_access auth helper.

Tests cover:
- Valid member returns membership record with correct role
- Non-member receives HTTP 404 (does not leak circle existence)
- Role filter passes when user's role is in the allowed list
- Role filter fails with HTTP 403 when role is not in the allowed list

Fixture: 3 users, 1 patient, 1 circle, 2 members
  - primary_caregiver_user → role "primary_caregiver"
  - family_user            → role "family"
  - outsider_user          → not in circle at all

@decision DEC-CIRCLE-AUTH-001
@title 404 for non-members instead of 403 to avoid leaking circle existence
@status accepted
@rationale Returning 404 to non-members means an attacker cannot distinguish
    "circle does not exist" from "you are not a member", preventing enumeration
    of valid circle IDs. This mirrors the _resolve_caregiver_patient pattern
    already established in auth.py.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException

from ada.api.auth import resolve_circle_access
from ada.core.state import StateManager
from ada.models.user import User


# ---------------------------------------------------------------------------
# Fixed IDs
# ---------------------------------------------------------------------------

_CIRCLE_ID = "circle-test-001"
_PATIENT_ID = "patient-test-001"

_PC_USER_ID = "user-pc-001"
_PC_EMAIL = "primary@example.com"

_FAM_USER_ID = "user-fam-001"
_FAM_EMAIL = "family@example.com"

_OUTSIDER_ID = "user-out-001"
_OUTSIDER_EMAIL = "outsider@example.com"

_PC_MEMBER_ID = "ccm-pc-001"
_FAM_MEMBER_ID = "ccm-fam-001"


# ---------------------------------------------------------------------------
# User stubs
# ---------------------------------------------------------------------------

def _make_user(user_id: str, email: str) -> User:
    from datetime import datetime
    return User(
        id=user_id,
        email=email,
        role="caregiver",
        patient_id=None,
        created_at=datetime.utcnow(),
        is_active=True,
    )


_PC_USER = _make_user(_PC_USER_ID, _PC_EMAIL)
_FAM_USER = _make_user(_FAM_USER_ID, _FAM_EMAIL)
_OUTSIDER_USER = _make_user(_OUTSIDER_ID, _OUTSIDER_EMAIL)


# ---------------------------------------------------------------------------
# Shared fixture: seeded in-memory StateManager
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    """
    In-memory StateManager seeded with:
      - 3 users (primary_caregiver, family, outsider)
      - 1 patient
      - 1 care circle
      - 2 members (primary_caregiver + family)
    """
    sm = StateManager(":memory:")
    await sm.initialize()

    # Users — hashed_password is a placeholder (not tested here)
    for uid, email in [
        (_PC_USER_ID, _PC_EMAIL),
        (_FAM_USER_ID, _FAM_EMAIL),
        (_OUTSIDER_ID, _OUTSIDER_EMAIL),
    ]:
        await sm.create_user({
            "id": uid,
            "email": email,
            "hashed_password": "x",
            "role": "caregiver",
        })

    # Patient
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Test Patient",
        "dob": "1990-01-01",
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })

    # Care circle
    await sm.create_care_circle(_CIRCLE_ID, _PATIENT_ID)

    # Members
    await sm.add_circle_member(
        member_id=_PC_MEMBER_ID,
        circle_id=_CIRCLE_ID,
        user_id=_PC_USER_ID,
        role="primary_caregiver",
        added_by=None,
    )
    await sm.add_circle_member(
        member_id=_FAM_MEMBER_ID,
        circle_id=_CIRCLE_ID,
        user_id=_FAM_USER_ID,
        role="family",
        added_by=_PC_USER_ID,
    )

    yield sm
    await sm.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_member(state: StateManager) -> None:
    """resolve_circle_access returns membership dict with correct role."""
    member = await resolve_circle_access(_PC_USER, _CIRCLE_ID, state)
    assert member["user_id"] == _PC_USER_ID
    assert member["role"] == "primary_caregiver"


@pytest.mark.asyncio
async def test_non_member_404(state: StateManager) -> None:
    """Outsider (not in circle) receives HTTP 404."""
    with pytest.raises(HTTPException) as exc_info:
        await resolve_circle_access(_OUTSIDER_USER, _CIRCLE_ID, state)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_role_filter_pass(state: StateManager) -> None:
    """primary_caregiver passes the ["primary_caregiver", "clinician"] filter."""
    member = await resolve_circle_access(
        _PC_USER,
        _CIRCLE_ID,
        state,
        require_roles=["primary_caregiver", "clinician"],
    )
    assert member["role"] == "primary_caregiver"


@pytest.mark.asyncio
async def test_role_filter_fail(state: StateManager) -> None:
    """family member fails the ["primary_caregiver"] filter with HTTP 403."""
    with pytest.raises(HTTPException) as exc_info:
        await resolve_circle_access(
            _FAM_USER,
            _CIRCLE_ID,
            state,
            require_roles=["primary_caregiver"],
        )
    assert exc_info.value.status_code == 403
