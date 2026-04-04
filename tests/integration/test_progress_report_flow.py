"""Integration test: progress report endpoint end-to-end.

Creates a patient with sessions, assessments, medications, and emotion
analyses via StateManager, then hits the progress report endpoint and
verifies the response has all expected data sections populated.

Uses real JWT auth (no dependency_overrides), same pattern as
test_patient_dashboard_flow.py.

@decision DEC-VIZ-003
@title Progress report integration test uses real auth + real SQLite
@status accepted
@rationale Full vertical slice: register, login, seed clinical data, request
    report, verify all aggregation sections. Ensures auth guards and state
    aggregation work together end-to-end.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.routes.progress_report import clear_cache
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router


# ---------------------------------------------------------------------------
# LLM stub
# ---------------------------------------------------------------------------


class _StubLLM(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        return LLMResponse(
            content="Overall, the patient demonstrates steady progress.",
            model="stub",
            input_tokens=0,
            output_tokens=0,
        )

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# App / client factory
# ---------------------------------------------------------------------------


def _make_client(state: StateManager) -> TestClient:
    config = AdaConfig()
    bus = EventBus()
    registry = AgentRegistry(bus, config, state, make_null_router(_StubLLM()))
    app = create_app(config, bus, state, registry)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def register_and_login(client: TestClient, email: str, password: str, role: str = "user") -> str:
    """Register a user and return a JWT access token."""
    client.post("/api/auth/register", json={"email": email, "password": password, "role": role})
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed ({resp.status_code}): {resp.text}"
    return resp.json()["access_token"]


def setup_circle(client: TestClient) -> tuple[str, str, str]:
    """Register patient + caregiver, create circle.

    Returns (patient_token, cg_token, patient_id).
    """
    patient_token = register_and_login(client, "patient@test.com", "TestPass1234", "user")
    cg_token = register_and_login(client, "cg@test.com", "CgPass1234", "caregiver")

    resp = client.post(
        "/api/circles/create-with-patient",
        json={"patient_name": "Report Patient", "patient_email": "patient@test.com"},
        headers={"Authorization": f"Bearer {cg_token}"},
    )
    assert resp.status_code == 201, f"Circle creation failed ({resp.status_code}): {resp.text}"
    patient_id = resp.json()["patient_id"]
    return patient_token, cg_token, patient_id


async def seed_clinical_data(state: StateManager, patient_id: str) -> None:
    """Seed sessions, emotions, assessments, medications via StateManager."""
    # Session
    await state.create_session({
        "id": "sess-int-001",
        "patient_id": patient_id,
        "started_at": "2026-03-20T10:00:00",
        "ended_at": "2026-03-20T11:00:00",
        "summary": "",
        "mood_start": None,
        "mood_end": None,
    })

    # Emotion analysis
    await state.create_emotion_analysis({
        "id": str(uuid.uuid4()),
        "session_id": "sess-int-001",
        "patient_id": patient_id,
        "message_id": "msg-int-001",
        "primary_emotion": "hopeful",
        "secondary_emotion": None,
        "intensity": 0.6,
        "valence": 0.7,
        "arousal": 0.4,
        "confidence": 0.88,
    })

    # Assessment: PHQ-9
    await state.save_assessment({
        "id": str(uuid.uuid4()),
        "patient_id": patient_id,
        "instrument": "phq9",
        "item_scores": "[1,1,0,1,0,1,0,0,0]",
        "total_score": 4,
        "severity": "minimal",
        "timestamp": "2026-03-20T12:00:00",
    })

    # Assessment: WHO-5
    await state.save_assessment({
        "id": str(uuid.uuid4()),
        "patient_id": patient_id,
        "instrument": "who5",
        "item_scores": "[4,4,3,4,3]",
        "total_score": 18,
        "severity": "high",
        "timestamp": "2026-03-20T12:00:00",
    })

    # Medication + log
    med_id = str(uuid.uuid4())
    await state.create_medication({
        "id": med_id,
        "patient_id": patient_id,
        "name": "Fluoxetine",
        "dosage": "20mg",
        "frequency": "daily",
        "active": True,
        "notes": None,
        "prescribed_by": None,
        "started_at": None,
    })
    await state.create_medication_log({
        "id": str(uuid.uuid4()),
        "medication_id": med_id,
        "patient_id": patient_id,
        "taken_at": "2026-03-20T08:00:00",
        "status": "taken",
        "created_at": "2026-03-20T08:00:00",
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_progress_report_flow(state: StateManager):
    """End-to-end: create patient with data, request progress report, verify all sections."""
    with _make_client(state) as client:
        patient_token, _cg_token, patient_id = setup_circle(client)

        # Seed clinical data (async, but TestClient uses the same event loop
        # via aiosqlite's thread bridge, so we can await directly here before
        # the sync HTTP calls)
        await seed_clinical_data(state, patient_id)

        headers = {"Authorization": f"Bearer {patient_token}"}

        resp = client.get(
            f"/api/patients/{patient_id}/progress-report?range=all",
            headers=headers,
        )
        assert resp.status_code == 200, f"Progress report failed ({resp.status_code}): {resp.text}"
        data = resp.json()

        # All top-level keys present
        assert "narrative" in data
        assert "who5_trend" in data
        assert "session_count_by_week" in data
        assert "emotion_distribution" in data
        assert "medication_adherence" in data
        assert "assessment_scores" in data
        assert "flags" in data

        # Narrative generated
        assert len(data["narrative"]) > 0

        # Sessions: 1 session
        assert len(data["session_count_by_week"]) >= 1

        # Emotions: hopeful
        assert "hopeful" in data["emotion_distribution"]

        # Medication adherence: 1 taken, 1 total
        assert data["medication_adherence"]["taken"] == 1
        assert data["medication_adherence"]["total"] == 1

        # PHQ-9 score
        assert "phq9" in data["assessment_scores"]
        assert data["assessment_scores"]["phq9"]["current"] == 4
        assert data["assessment_scores"]["phq9"]["severity"] == "minimal"

        # WHO-5 trend
        assert len(data["who5_trend"]) >= 1
        assert data["who5_trend"][0]["score"] == 18 * 4  # 72


@pytest.mark.asyncio
async def test_caregiver_can_access_patient_report(state: StateManager):
    """Caregiver role can also request a patient's progress report."""
    with _make_client(state) as client:
        _patient_token, cg_token, patient_id = setup_circle(client)
        await seed_clinical_data(state, patient_id)
        headers = {"Authorization": f"Bearer {cg_token}"}

        resp = client.get(
            f"/api/patients/{patient_id}/progress-report?range=2w",
            headers=headers,
        )
        assert resp.status_code == 200, f"Caregiver access failed ({resp.status_code}): {resp.text}"
        data = resp.json()
        assert "narrative" in data


@pytest.mark.asyncio
async def test_report_range_filtering(state: StateManager):
    """Verify range=all returns populated data sections."""
    with _make_client(state) as client:
        patient_token, _cg_token, patient_id = setup_circle(client)
        await seed_clinical_data(state, patient_id)
        headers = {"Authorization": f"Bearer {patient_token}"}

        # With 'all', we get data
        resp_all = client.get(
            f"/api/patients/{patient_id}/progress-report?range=all",
            headers=headers,
        )
        assert resp_all.status_code == 200
        data_all = resp_all.json()

        # Response should have assessments and sessions
        assert len(data_all["session_count_by_week"]) >= 1
        assert len(data_all["assessment_scores"]) >= 1
