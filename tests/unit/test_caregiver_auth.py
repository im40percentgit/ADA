"""Tests for caregiver role and authorization."""
import pytest
from ada.models.user import Role, UserCreate


def test_caregiver_role_accepted():
    user = UserCreate(email="cg@test.com", password="Test1234!", role="caregiver")
    assert user.role == "caregiver"


def test_invalid_role_rejected():
    with pytest.raises(Exception):
        UserCreate(email="x@test.com", password="Test1234!", role="bogus")


# @mock-exempt: state_manager is a DB-backed external boundary for the auth module;
# these tests isolate _resolve_caregiver_patient logic without a real SQLite instance.
import pytest
from unittest.mock import AsyncMock
from fastapi import HTTPException
from ada.api.auth import _resolve_caregiver_patient
from ada.models.user import User
from datetime import datetime


@pytest.mark.asyncio
async def test_caregiver_can_access_own_patient():
    """Caregiver whose ID matches patient.caregiver_id should get the patient_id back.

    get_patients_by_circle_member returns [] (no circle yet) so the legacy
    get_patient_by_caregiver fallback is exercised.
    """
    state = AsyncMock()
    state.get_patients_by_circle_member.return_value = []
    state.get_patient_by_caregiver.return_value = {"id": "patient-1", "caregiver_id": "cg-1", "name": "Mom"}
    result = await _resolve_caregiver_patient(
        user=User(id="cg-1", email="cg@test.com", role="caregiver", patient_id=None, created_at=datetime.now(), is_active=True),
        state_manager=state,
    )
    assert result == "patient-1"


@pytest.mark.asyncio
async def test_caregiver_with_no_linked_patient_gets_404():
    """Caregiver with no patient linked should get 404 (neither circle nor legacy record)."""
    state = AsyncMock()
    state.get_patients_by_circle_member.return_value = []
    state.get_patient_by_caregiver.return_value = None
    with pytest.raises(HTTPException) as exc:
        await _resolve_caregiver_patient(
            user=User(id="cg-orphan", email="cg@test.com", role="caregiver", patient_id=None, created_at=datetime.now(), is_active=True),
            state_manager=state,
        )
    assert exc.value.status_code == 404
