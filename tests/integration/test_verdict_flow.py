"""
Integration test: verdict API full vertical slice — Phase 15+ M3.

Tests exercise the complete HTTP → StateManager → verdict generator → DB path
using a real in-memory SQLite StateManager and a real FastAPI TestClient.

Coverage:
  - POST /api/verdict/generate → 200, verdict row returned
  - POST /api/verdict/generate idempotency (same date twice → same row)
  - POST /api/verdict/generate with NO_SIGNAL (no sessions)
  - GET  /api/verdict/unlabeled returns unlabeled rows oldest-first
  - POST /api/verdict/{id}/label → labeled_truth set, row disappears from unlabeled
  - GET  /api/verdict/calibration → correct streak/FP/FN/ratio/gate computation

LLM is stubbed (external boundary per DEC-TEST-005).

@decision DEC-TEST-005
@title Mock only external boundaries (LLM API), not internal modules
@status accepted
@rationale Full HTTP→DB slice validated without mocking any internal module.
    Only the LLMProvider is stubbed — it represents a live Anthropic API call.
    Pattern mirrors test_games_flow.py and test_daily_summary_flow.py.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Generator

import pytest
import pytest_asyncio

from fastapi.testclient import TestClient

from ada.agents.registry import AgentRegistry
from ada.api.app import create_app
from ada.api.auth import get_current_user
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import EventTypes
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.router import make_null_router
from ada.models.user import User

# ---------------------------------------------------------------------------
# LLM stub
# ---------------------------------------------------------------------------

# @mock-exempt: LLMProvider is an external HTTP boundary (Anthropic API).
# Stubbing follows DEC-TEST-005 — real API calls are not appropriate in CI.


class _VerdictLLM(LLMProvider):
    """Deterministic LLM stub that returns a configurable verdict JSON."""

    def __init__(self, verdict: str = "OK", explanation: str = "Session within normal range.", dimension: str | None = "none") -> None:
        self._verdict = verdict
        self._explanation = explanation
        self._dimension = dimension
        self.call_count = 0

    async def complete(self, messages, **kwargs) -> LLMResponse:
        self.call_count += 1
        content = json.dumps({
            "verdict": self._verdict,
            "explanation": self._explanation,
            "dimension": self._dimension,
        })
        return LLMResponse(content=content, model="claude-stub", input_tokens=50, output_tokens=30)

    async def stream(self, messages, **kwargs):
        return
        yield


class _FailingLLM(LLMProvider):
    """LLM stub that always raises — used to test synthetic UNSURE fallback."""

    async def complete(self, messages, **kwargs) -> LLMResponse:
        raise RuntimeError("Simulated LLM outage")

    async def stream(self, messages, **kwargs):
        return
        yield


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATIENT_ID = "pat-verdict-flow-001"
_TODAY = "2026-04-24"
_YESTERDAY = "2026-04-23"

_ADMIN_USER = User(
    id="user-verdict-flow-001",
    email="founder@example.com",
    role="admin",
    patient_id=None,
    created_at=datetime.utcnow(),
    is_active=True,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    """In-memory StateManager with a seeded patient."""
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Verdict Flow Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


@contextmanager
def _make_client(
    sm: StateManager,
    user: User,
    llm: LLMProvider | None = None,
) -> Generator[TestClient, None, None]:
    config = AdaConfig()
    bus = EventBus()
    stub = llm or _VerdictLLM()
    registry = AgentRegistry(bus, config, sm, make_null_router(stub))
    app = create_app(config, bus, sm, registry)
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


async def _seed_session(sm: StateManager, occurred_at: str) -> None:
    """Insert a game.session_end event for the test patient."""
    await sm.create_game_session_event({
        "patient_id": _PATIENT_ID,
        "event_type": EventTypes.GAME_SESSION_END,
        "payload": {
            "game_session_id": f"gs-{occurred_at}",
            "duration_ms": 300_000,
            "completed_hands": 1,
            "error_count": 3,
            "end_reason": "completed",
            "deck": "corgi",
            "total_moves": 60,
            "total_undo_count": 2,
            "total_invalid_click_count": 1,
            "total_idle_ms": 30_000,
            "restart_count_today": 0,
        },
        "occurred_at": occurred_at,
    })


# ---------------------------------------------------------------------------
# POST /api/verdict/generate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_verdict_returns_verdict_row(state):
    """POST generate with sessions → 200 + verdict row with all expected fields."""
    await _seed_session(state, f"{_TODAY}T20:00:00")

    with _make_client(state, _ADMIN_USER) as client:
        resp = client.post("/api/verdict/generate", json={
            "patient_id": _PATIENT_ID,
            "date": _TODAY,
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] in ("OK", "OFF", "UNSURE", "NO_SIGNAL")
    assert body["patient_id"] == _PATIENT_ID
    assert body["verdict_date"] == _TODAY
    assert body["prompt_version"] == "v1"
    assert isinstance(body["telemetry_summary"], dict)
    assert body["id"] is not None


@pytest.mark.asyncio
async def test_generate_verdict_no_signal_when_no_sessions(state):
    """POST generate with no sessions → NO_SIGNAL (no LLM call)."""
    llm = _VerdictLLM()

    with _make_client(state, _ADMIN_USER, llm) as client:
        resp = client.post("/api/verdict/generate", json={
            "patient_id": _PATIENT_ID,
            "date": _TODAY,
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "NO_SIGNAL"
    assert llm.call_count == 0  # LLM should not have been called


@pytest.mark.asyncio
async def test_generate_verdict_idempotent(state):
    """Calling generate twice for same date returns the same verdict (single DB row)."""
    await _seed_session(state, f"{_TODAY}T20:00:00")

    with _make_client(state, _ADMIN_USER) as client:
        resp1 = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _TODAY})
        resp2 = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _TODAY})

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["verdict"] == resp2.json()["verdict"]
    assert resp1.json()["verdict_date"] == resp2.json()["verdict_date"]


@pytest.mark.asyncio
async def test_generate_verdict_llm_failure_produces_synthetic_unsure(state):
    """All 3 LLM retries fail → synthetic UNSURE persisted with 'check in' explanation."""
    await _seed_session(state, f"{_TODAY}T20:00:00")

    with _make_client(state, _ADMIN_USER, _FailingLLM()) as client:
        resp = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _TODAY})

    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "UNSURE"
    assert "check in" in body["explanation"].lower()


@pytest.mark.asyncio
async def test_generate_verdict_404_for_missing_patient(state):
    """POST generate for a non-existent patient → 404."""
    with _make_client(state, _ADMIN_USER) as client:
        resp = client.post("/api/verdict/generate", json={"patient_id": "no-such-patient"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_verdict_422_for_bad_date(state):
    """POST generate with invalid date string → 422."""
    with _make_client(state, _ADMIN_USER) as client:
        resp = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": "not-a-date"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/verdict/unlabeled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unlabeled_returns_oldest_first(state):
    """GET unlabeled returns rows ordered oldest-first."""
    await _seed_session(state, f"{_TODAY}T20:00:00")
    await _seed_session(state, f"{_YESTERDAY}T20:00:00")

    with _make_client(state, _ADMIN_USER) as client:
        # Generate both verdicts
        client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _TODAY})
        client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _YESTERDAY})

        resp = client.get(f"/api/verdict/unlabeled?patient_id={_PATIENT_ID}")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 2
    dates = [r["verdict_date"] for r in rows]
    # Oldest first: yesterday before today
    assert dates.index(_YESTERDAY) < dates.index(_TODAY)


# ---------------------------------------------------------------------------
# POST /api/verdict/{id}/label
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_label_verdict_sets_truth_and_disappears_from_unlabeled(state):
    """Label a verdict → labeled_truth set, row gone from unlabeled list."""
    await _seed_session(state, f"{_TODAY}T20:00:00")

    with _make_client(state, _ADMIN_USER) as client:
        gen_resp = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _TODAY})
        verdict_id = gen_resp.json()["id"]

        label_resp = client.post(
            f"/api/verdict/{verdict_id}/label",
            json={"label": "TRUTH_OK", "labeled_by": "founder@example.com"},
        )
        assert label_resp.status_code == 200
        labeled = label_resp.json()
        assert labeled["labeled_truth"] == "TRUTH_OK"
        assert labeled["labeled_by"] == "founder@example.com"
        assert labeled["labeled_at"] is not None

        # Row should no longer appear in unlabeled list
        unlabeled_resp = client.get(f"/api/verdict/unlabeled?patient_id={_PATIENT_ID}")
        unlabeled_ids = [r["id"] for r in unlabeled_resp.json()]
        assert verdict_id not in unlabeled_ids


@pytest.mark.asyncio
async def test_label_verdict_invalid_label_422(state):
    """POST label with invalid label value → 422."""
    await _seed_session(state, f"{_TODAY}T20:00:00")

    with _make_client(state, _ADMIN_USER) as client:
        gen_resp = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _TODAY})
        verdict_id = gen_resp.json()["id"]

        resp = client.post(f"/api/verdict/{verdict_id}/label", json={"label": "WRONG_LABEL"})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_label_verdict_404_for_missing_id(state):
    """POST label for non-existent verdict_id → 404."""
    with _make_client(state, _ADMIN_USER) as client:
        resp = client.post("/api/verdict/99999/label", json={"label": "TRUTH_OK"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/verdict/calibration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calibration_empty_state(state):
    """Calibration endpoint with no verdicts → all zeros, gate_passed=False."""
    with _make_client(state, _ADMIN_USER) as client:
        resp = client.get(f"/api/verdict/calibration?patient_id={_PATIENT_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["labeled_streak_days"] == 0
    assert body["labeled_streak_target"] == 21
    assert body["last7_false_ok_count"] == 0
    assert body["last7_false_off_count"] == 0
    assert body["gate_passed"] is False


@pytest.mark.asyncio
async def test_calibration_streak_counting(state):
    """Labeled consecutive days count toward the streak."""
    # Generate and label 3 consecutive days
    days = [date(2026, 4, 22), date(2026, 4, 23), date(2026, 4, 24)]
    verdict_ids = []

    with _make_client(state, _ADMIN_USER) as client:
        for d in days:
            await _seed_session(state, f"{d.isoformat()}T20:00:00")
            resp = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": d.isoformat()})
            verdict_ids.append(resp.json()["id"])

        # Label all three
        for vid in verdict_ids:
            client.post(f"/api/verdict/{vid}/label", json={"label": "TRUTH_OK"})

        cal_resp = client.get(f"/api/verdict/calibration?patient_id={_PATIENT_ID}")

    body = cal_resp.json()
    assert body["labeled_streak_days"] == 3
    assert body["gate_passed"] is False  # < 21 days


@pytest.mark.asyncio
async def test_calibration_false_ok_detection(state):
    """Verdict=OK + label=TRUTH_OFF in last 7 counted as false OK (false negative)."""
    await _seed_session(state, f"{_TODAY}T20:00:00")

    # Force OK verdict from LLM
    ok_llm = _VerdictLLM(verdict="OK", explanation="Normal session length today.", dimension="none")

    with _make_client(state, _ADMIN_USER, ok_llm) as client:
        gen_resp = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _TODAY})
        verdict_id = gen_resp.json()["id"]

        # Label it as TRUTH_OFF (we said OK but patient was actually OFF)
        client.post(f"/api/verdict/{verdict_id}/label", json={"label": "TRUTH_OFF"})

        cal_resp = client.get(f"/api/verdict/calibration?patient_id={_PATIENT_ID}")

    body = cal_resp.json()
    assert body["last7_false_ok_count"] == 1
    assert body["gate_passed"] is False


@pytest.mark.asyncio
async def test_calibration_false_off_detection(state):
    """Verdict=OFF + label=TRUTH_OK in last 7 counted as false OFF (false positive)."""
    await _seed_session(state, f"{_TODAY}T20:00:00")

    # Force OFF verdict with a dimension so it passes bias-toward-UNSURE
    off_llm = _VerdictLLM(verdict="OFF", explanation="Session significantly shorter than baseline.", dimension="lethargy")

    with _make_client(state, _ADMIN_USER, off_llm) as client:
        gen_resp = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": _TODAY})
        verdict_id = gen_resp.json()["id"]

        # Label it as TRUTH_OK (we said OFF but patient was actually OK)
        client.post(f"/api/verdict/{verdict_id}/label", json={"label": "TRUTH_OK"})

        cal_resp = client.get(f"/api/verdict/calibration?patient_id={_PATIENT_ID}")

    body = cal_resp.json()
    assert body["last7_false_off_count"] == 1
    assert body["gate_passed"] is False


@pytest.mark.asyncio
async def test_calibration_unsure_no_signal_ratio(state):
    """all_unsure_no_signal_ratio = (UNSURE + NO_SIGNAL) / total."""
    # Generate 2 NO_SIGNAL days (no sessions seeded) and 0 OK days
    days_no_signal = [date(2026, 4, 22), date(2026, 4, 23)]

    with _make_client(state, _ADMIN_USER) as client:
        for d in days_no_signal:
            client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": d.isoformat()})

        cal_resp = client.get(f"/api/verdict/calibration?patient_id={_PATIENT_ID}")

    body = cal_resp.json()
    # Both are NO_SIGNAL → ratio = 2/2 = 1.0
    assert body["all_unsure_no_signal_ratio"] == pytest.approx(1.0, rel=1e-3)


@pytest.mark.asyncio
async def test_calibration_gate_passes_when_all_conditions_met(state):
    """gate_passed = True only when all 4 conditions are satisfied."""
    # We need 21 labeled days with zero FP/FN and ratio <= 0.30.
    # Seed 21 OK-verdict days and label them all TRUTH_OK.
    ok_llm = _VerdictLLM(verdict="OK", explanation="Session within normal range.", dimension="none")

    base_date = date(2026, 3, 1)
    verdict_ids = []

    with _make_client(state, _ADMIN_USER, ok_llm) as client:
        for i in range(21):
            d = base_date + timedelta(days=i)
            await _seed_session(state, f"{d.isoformat()}T20:00:00")
            resp = client.post("/api/verdict/generate", json={"patient_id": _PATIENT_ID, "date": d.isoformat()})
            verdict_ids.append(resp.json()["id"])

        # Label all 21 as TRUTH_OK (most recent first for streak)
        for vid in reversed(verdict_ids):
            client.post(f"/api/verdict/{vid}/label", json={"label": "TRUTH_OK"})

        cal_resp = client.get(f"/api/verdict/calibration?patient_id={_PATIENT_ID}")

    body = cal_resp.json()
    assert body["labeled_streak_days"] >= 21
    assert body["last7_false_ok_count"] == 0
    assert body["last7_false_off_count"] == 0
    assert body["all_unsure_no_signal_ratio"] <= 0.30
    assert body["gate_passed"] is True
