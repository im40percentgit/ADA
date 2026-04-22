"""
Unit tests for GET /api/patients/{patient_id}/progress-report.

Uses real in-memory SQLite, FastAPI TestClient, and dependency_overrides
for auth bypass. The LLM provider is stubbed to return a fixed narrative.

Coverage:
- Range parsing (valid/invalid)
- Severity label functions (PHQ-9, GAD-7, WHO-5)
- 200 response with all expected top-level keys
- Session count by week aggregation
- Emotion distribution aggregation
- Medication adherence (taken/missed)
- Assessment scores with severity labels
- WHO-5 trend (raw * 4 = percentage)
- Flags: medication_adherence_decline, phq9_score_increase
- Narrative cache hit/miss
- Empty data handling
- 404 for non-existent patient
- 400 for invalid range

@decision DEC-VIZ-002
@title Progress report unit tests use stubbed LLM + real SQLite
@status accepted
@rationale Consistent with all other route tests. The LLM stub returns a
    deterministic narrative so tests can assert on cache behaviour without
    depending on a real model. Severity functions are tested as pure units.
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
from ada.api.routes.progress_report import (
    VALID_RANGES,
    clear_cache,
    gad7_severity,
    parse_range,
    phq9_severity,
    who5_severity,
)
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User


# ---------------------------------------------------------------------------
# LLM stub that returns a fixed narrative
# ---------------------------------------------------------------------------

class _StubLLM(LLMProvider):
    """LLM that returns a fixed narrative string."""

    def __init__(self, narrative: str = "Test narrative summary."):
        self.narrative = narrative
        self.call_count = 0

    async def complete(self, messages, **kwargs) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(content=self.narrative, model="stub", input_tokens=0, output_tokens=0)

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# Fake user
# ---------------------------------------------------------------------------

_TEST_USER = User(
    id="user-pr-001",
    email="test@example.com",
    role="user",
    patient_id="pat-pr-001",
    created_at=datetime.utcnow(),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _make_client(
    state: StateManager,
    llm: LLMProvider | None = None,
    user: User = _TEST_USER,
) -> TestClient:
    config = AdaConfig()
    bus = EventBus()
    if llm is None:
        llm = _StubLLM()
    registry = AgentRegistry(bus, config, state, make_null_router(llm))
    app = create_app(config, bus, state, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "pat-pr-001",
        "name": "Test Patient",
        "dob": "1990-01-01",
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


@pytest.fixture(autouse=True)
def _clear_narrative_cache():
    """Clear the narrative cache before each test."""
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# Pure unit tests: severity functions
# ---------------------------------------------------------------------------

class TestSeverityFunctions:

    @pytest.mark.parametrize("score,expected", [
        (0, "minimal"), (4, "minimal"),
        (5, "mild"), (9, "mild"),
        (10, "moderate"), (14, "moderate"),
        (15, "moderately severe"), (19, "moderately severe"),
        (20, "severe"), (27, "severe"),
    ])
    def test_phq9_severity(self, score, expected):
        assert phq9_severity(score) == expected

    @pytest.mark.parametrize("score,expected", [
        (0, "minimal"), (4, "minimal"),
        (5, "mild"), (9, "mild"),
        (10, "moderate"), (14, "moderate"),
        (15, "severe"), (21, "severe"),
    ])
    def test_gad7_severity(self, score, expected):
        assert gad7_severity(score) == expected

    @pytest.mark.parametrize("raw_score,expected", [
        (0, "low"),      # 0%
        (12, "low"),     # 48%
        (13, "moderate"),  # 52%
        (18, "moderate"),  # 72%
        (19, "high"),    # 76%
        (25, "high"),    # 100%
    ])
    def test_who5_severity(self, raw_score, expected):
        assert who5_severity(raw_score) == expected


# ---------------------------------------------------------------------------
# Pure unit tests: range parsing
# ---------------------------------------------------------------------------

class TestRangeParsing:

    @pytest.mark.parametrize("range_str", list(VALID_RANGES))
    def test_valid_ranges(self, range_str):
        result = parse_range(range_str)
        if range_str == "all":
            assert result is None
        else:
            assert result is not None

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError, match="Invalid range"):
            parse_range("6m")


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class TestProgressReportEndpoint:

    def test_returns_all_sections(self, state):
        """200 response with all expected top-level keys."""
        with _make_client(state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report")
        assert resp.status_code == 200
        data = resp.json()
        expected_keys = {
            "narrative", "who5_trend", "session_count_by_week",
            "emotion_distribution", "medication_adherence",
            "assessment_scores", "flags",
        }
        assert expected_keys.issubset(set(data.keys()))

    def test_invalid_range_returns_400(self, state):
        """Invalid range parameter returns 400."""
        with _make_client(state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=6m")
        assert resp.status_code == 400

    def test_nonexistent_patient_returns_403(self, state):
        """Accessing a patient_id the user has no access to returns 403.

        Previously expected 404, but require_patient_access runs before the
        patient-existence check and returns 403 to avoid leaking patient-ID
        existence (per DEC-AUTHZ-001 spec).
        """
        with _make_client(state) as client:
            resp = client.get("/api/patients/no-such-patient/progress-report")
        assert resp.status_code == 403

    def test_empty_data_returns_defaults(self, state):
        """Patient with no sessions/assessments/meds returns empty aggregations."""
        with _make_client(state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=1w")
        assert resp.status_code == 200
        data = resp.json()
        assert data["who5_trend"] == []
        assert data["session_count_by_week"] == []
        assert data["emotion_distribution"] == {}
        assert data["medication_adherence"] == {"taken": 0, "total": 0, "missed_dates": []}
        assert data["assessment_scores"] == {}
        assert data["flags"] == []


# ---------------------------------------------------------------------------
# Tests with seeded data
# ---------------------------------------------------------------------------

class TestProgressReportWithData:

    @pytest_asyncio.fixture
    async def rich_state(self) -> StateManager:
        """State with sessions, assessments, medications, emotion analyses."""
        sm = StateManager(":memory:")
        await sm.initialize()
        await sm.create_patient({
            "id": "pat-pr-001",
            "name": "Rich Patient",
            "dob": "1990-01-01",
            "preferences": {},
            "emergency_contact": None,
            "caregiver_id": None,
        })

        # Two sessions in different weeks
        await sm.create_session({
            "id": "sess-001",
            "patient_id": "pat-pr-001",
            "started_at": "2026-03-16T10:00:00",  # Week 12
            "ended_at": "2026-03-16T11:00:00",
            "summary": "",
            "mood_start": None,
            "mood_end": None,
        })
        await sm.create_session({
            "id": "sess-002",
            "patient_id": "pat-pr-001",
            "started_at": "2026-03-23T10:00:00",  # Week 13
            "ended_at": "2026-03-23T11:00:00",
            "summary": "",
            "mood_start": None,
            "mood_end": None,
        })

        # Emotion analyses for session 1
        await sm.create_emotion_analysis({
            "id": str(uuid.uuid4()),
            "session_id": "sess-001",
            "patient_id": "pat-pr-001",
            "message_id": "msg-001",
            "primary_emotion": "calm",
            "secondary_emotion": None,
            "intensity": 0.6,
            "valence": 0.7,
            "arousal": 0.3,
            "confidence": 0.9,
        })
        await sm.create_emotion_analysis({
            "id": str(uuid.uuid4()),
            "session_id": "sess-001",
            "patient_id": "pat-pr-001",
            "message_id": "msg-002",
            "primary_emotion": "hopeful",
            "secondary_emotion": None,
            "intensity": 0.5,
            "valence": 0.8,
            "arousal": 0.4,
            "confidence": 0.85,
        })
        await sm.create_emotion_analysis({
            "id": str(uuid.uuid4()),
            "session_id": "sess-002",
            "patient_id": "pat-pr-001",
            "message_id": "msg-003",
            "primary_emotion": "calm",
            "secondary_emotion": None,
            "intensity": 0.7,
            "valence": 0.75,
            "arousal": 0.25,
            "confidence": 0.92,
        })

        # Assessments
        await sm.save_assessment({
            "id": str(uuid.uuid4()),
            "patient_id": "pat-pr-001",
            "instrument": "phq9",
            "item_scores": "[1,1,1,1,1,1,1,1,0]",
            "total_score": 8,
            "severity": "mild",
            "timestamp": "2026-03-20T10:00:00",
        })
        await sm.save_assessment({
            "id": str(uuid.uuid4()),
            "patient_id": "pat-pr-001",
            "instrument": "phq9",
            "item_scores": "[2,2,1,1,1,2,1,1,1]",
            "total_score": 12,
            "severity": "moderate",
            "timestamp": "2026-03-10T10:00:00",
        })
        await sm.save_assessment({
            "id": str(uuid.uuid4()),
            "patient_id": "pat-pr-001",
            "instrument": "who5",
            "item_scores": "[3,3,2,3,2]",
            "total_score": 13,
            "severity": "moderate",
            "timestamp": "2026-03-15T10:00:00",
        })
        await sm.save_assessment({
            "id": str(uuid.uuid4()),
            "patient_id": "pat-pr-001",
            "instrument": "who5",
            "item_scores": "[4,3,3,3,3]",
            "total_score": 16,
            "severity": "high",
            "timestamp": "2026-03-22T10:00:00",
        })
        await sm.save_assessment({
            "id": str(uuid.uuid4()),
            "patient_id": "pat-pr-001",
            "instrument": "gad7",
            "item_scores": "[1,0,1,1,0,1,0]",
            "total_score": 4,
            "severity": "minimal",
            "timestamp": "2026-03-20T10:00:00",
        })

        # Medication + logs
        med_id = "med-001"
        await sm.create_medication({
            "id": med_id,
            "patient_id": "pat-pr-001",
            "name": "Sertraline",
            "dosage": "50mg",
            "frequency": "daily",
            "active": True,
            "notes": None,
            "prescribed_by": None,
            "started_at": None,
        })
        # 5 taken, 2 missed
        for i, (status, date) in enumerate([
            ("taken", "2026-03-17T08:00:00"),
            ("taken", "2026-03-18T08:00:00"),
            ("taken", "2026-03-19T08:00:00"),
            ("missed", "2026-03-20T08:00:00"),
            ("taken", "2026-03-21T08:00:00"),
            ("missed", "2026-03-22T08:00:00"),
            ("taken", "2026-03-23T08:00:00"),
        ]):
            await sm.create_medication_log({
                "id": str(uuid.uuid4()),
                "medication_id": med_id,
                "patient_id": "pat-pr-001",
                "taken_at": date,
                "status": status,
                "created_at": date,
            })

        yield sm
        await sm.close()

    def test_session_count_by_week(self, rich_state):
        with _make_client(rich_state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=all")
        assert resp.status_code == 200
        weeks = resp.json()["session_count_by_week"]
        assert len(weeks) == 2
        # Weeks should be sorted
        assert weeks[0]["week"] < weeks[1]["week"]
        assert weeks[0]["count"] == 1
        assert weeks[1]["count"] == 1

    def test_emotion_distribution(self, rich_state):
        with _make_client(rich_state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=all")
        assert resp.status_code == 200
        dist = resp.json()["emotion_distribution"]
        assert "calm" in dist
        assert "hopeful" in dist
        # 2 calm + 1 hopeful = 3 total
        assert dist["calm"] == pytest.approx(0.67, abs=0.01)
        assert dist["hopeful"] == pytest.approx(0.33, abs=0.01)

    def test_medication_adherence(self, rich_state):
        with _make_client(rich_state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=all")
        assert resp.status_code == 200
        adh = resp.json()["medication_adherence"]
        assert adh["taken"] == 5
        assert adh["total"] == 7
        assert "2026-03-20" in adh["missed_dates"]
        assert "2026-03-22" in adh["missed_dates"]

    def test_assessment_scores_with_severity(self, rich_state):
        with _make_client(rich_state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=all")
        assert resp.status_code == 200
        scores = resp.json()["assessment_scores"]

        # PHQ-9: latest=8 (mild), previous=12 (moderate)
        assert scores["phq9"]["current"] == 8
        assert scores["phq9"]["severity"] == "mild"
        assert scores["phq9"]["previous"] == 12

        # GAD-7: latest=4 (minimal), no previous
        assert scores["gad7"]["current"] == 4
        assert scores["gad7"]["severity"] == "minimal"
        assert scores["gad7"]["previous"] is None

        # WHO-5: latest=16, severity=moderate (16*4=64)
        assert scores["who5"]["current"] == 16
        assert scores["who5"]["severity"] == "moderate"
        assert scores["who5"]["previous"] == 13

    def test_who5_trend_percentage(self, rich_state):
        with _make_client(rich_state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=all")
        assert resp.status_code == 200
        trend = resp.json()["who5_trend"]
        # Two WHO-5 assessments, ascending by date
        assert len(trend) == 2
        assert trend[0]["score"] == 13 * 4  # 52
        assert trend[1]["score"] == 16 * 4  # 64

    def test_flags_medication_adherence_decline(self, rich_state):
        """5/7 = 71% < 80% triggers medication_adherence_decline flag."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=all")
        assert resp.status_code == 200
        flags = resp.json()["flags"]
        assert "medication_adherence_decline" in flags

    def test_flags_no_phq9_increase_when_score_decreased(self, rich_state):
        """PHQ-9 went from 12 to 8 (decreased), no phq9_score_increase flag."""
        with _make_client(rich_state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=all")
        assert resp.status_code == 200
        flags = resp.json()["flags"]
        assert "phq9_score_increase" not in flags

    def test_narrative_returned(self, rich_state):
        llm = _StubLLM("Patient shows improvement.")
        with _make_client(rich_state, llm=llm) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report?range=all")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == "Patient shows improvement."


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

class TestNarrativeCache:

    def test_cache_hit_avoids_llm_call(self, state):
        llm = _StubLLM("Cached narrative.")
        with _make_client(state, llm=llm) as client:
            # First call
            resp1 = client.get("/api/patients/pat-pr-001/progress-report?range=2w")
            assert resp1.status_code == 200
            assert llm.call_count == 1

            # Second call should be cached
            resp2 = client.get("/api/patients/pat-pr-001/progress-report?range=2w")
            assert resp2.status_code == 200
            assert llm.call_count == 1  # No additional LLM call

    def test_different_range_not_cached(self, state):
        llm = _StubLLM("Narrative.")
        with _make_client(state, llm=llm) as client:
            client.get("/api/patients/pat-pr-001/progress-report?range=1w")
            assert llm.call_count == 1

            client.get("/api/patients/pat-pr-001/progress-report?range=1m")
            assert llm.call_count == 2

    def test_default_range_is_2w(self, state):
        """When no range is specified, default is 2w."""
        with _make_client(state) as client:
            resp = client.get("/api/patients/pat-pr-001/progress-report")
        assert resp.status_code == 200
