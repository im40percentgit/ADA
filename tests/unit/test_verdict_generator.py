"""
Unit tests for the verdict generator subsystem — Phase 15+ M3.

Coverage:
  - NO_SIGNAL short-circuit when today+yesterday both empty (no LLM call)
  - Successful verdict with all fields persisted
  - Idempotency: same patient+date twice yields a single DB row
  - LLM failure x3 → synthetic UNSURE persisted (DEC-VERDICT-003)
  - Bias-toward-UNSURE: short explanation → UNSURE downgrade (DEC-VERDICT-004)
  - Bias-toward-UNSURE: OFF + no dimension → UNSURE downgrade (DEC-VERDICT-004)
  - Insufficient baseline → "insufficient" baseline_summary in DB row
  - Prompt builder fills both placeholders correctly
  - CLP feature extraction from session_end payload aggregates

LLM is mocked (external boundary per DEC-TEST-005 — real HTTP calls
are not appropriate in unit tests). StateManager uses in-memory SQLite.

@decision DEC-TEST-005
@title Mock only external boundaries (LLM API), not internal modules
@status accepted
@rationale Unit tests exercise real StateManager, real clp_features, real
    generator logic. Only the LLMProvider.complete() call is stubbed —
    it represents a real HTTP request to the Anthropic API which would
    be flaky and expensive in CI. Pattern mirrors test_games_routes.py.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from ada.core.events import EventTypes
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.verdict.clp_features import compute_baseline, compute_today_features
from ada.verdict.generator import _apply_bias_toward_unsure, generate_verdict_for_date
from ada.verdict.models import (
    VERDICT_NO_SIGNAL,
    VERDICT_OFF,
    VERDICT_OK,
    VERDICT_UNSURE,
    DailyVerdict,
)
from ada.verdict.prompt import PROMPT_VERSION, build_prompt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PATIENT_ID = "pat-verdict-unit-001"
_TODAY = date(2026, 4, 24)
_YESTERDAY = _TODAY - timedelta(days=1)


@pytest_asyncio.fixture
async def state():
    """In-memory StateManager with a seeded patient."""
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


def _make_llm(response_json: dict | None = None, *, fail_count: int = 0) -> LLMProvider:
    """
    Create a mock LLMProvider.

    # @mock-exempt: LLMProvider.complete() is an external HTTP boundary
    # (Anthropic API). Stubbing it here follows DEC-TEST-005 — real HTTP
    # calls are flaky, expensive, and require live credentials in CI.
    # All internal business logic (feature extraction, state persistence,
    # bias-toward-UNSURE post-processing) uses real implementations.

    Args:
        response_json: The JSON dict the LLM should return (serialised as
            the content string). Defaults to a valid OK verdict.
        fail_count: Number of times complete() raises before succeeding.
    """
    if response_json is None:
        response_json = {
            "verdict": "OK",
            "explanation": "Session length and decision time within normal range.",
            "dimension": "none",
        }

    call_count = 0

    async def _complete(messages, **kwargs) -> LLMResponse:
        nonlocal call_count
        call_count += 1
        if call_count <= fail_count:
            raise RuntimeError(f"Simulated LLM failure #{call_count}")
        return LLMResponse(
            content=json.dumps(response_json),
            model="claude-test",
            input_tokens=100,
            output_tokens=50,
        )

    mock = MagicMock(spec=LLMProvider)
    mock.complete = _complete
    return mock


async def _seed_session(state: StateManager, occurred_at: str, payload: dict | None = None) -> None:
    """Helper: insert a game.session_end event for _PATIENT_ID."""
    default_payload = {
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
    }
    if payload:
        default_payload.update(payload)
    await state.create_game_session_event({
        "patient_id": _PATIENT_ID,
        "event_type": EventTypes.GAME_SESSION_END,
        "payload": default_payload,
        "occurred_at": occurred_at,
    })


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_fills_telemetry_placeholder(self):
        telemetry = {"avg_decision_time_ms": 1234.0, "error_rate": 0.05}
        result = build_prompt(telemetry, "insufficient")
        assert '"avg_decision_time_ms": 1234.0' in result

    def test_fills_baseline_insufficient_string(self):
        result = build_prompt({"total_sessions": 1}, "insufficient")
        assert "insufficient" in result

    def test_fills_baseline_dict(self):
        baseline = {"avg_decision_time_ms_mean": 900.0}
        result = build_prompt({"total_sessions": 2}, baseline)
        assert '"avg_decision_time_ms_mean": 900.0' in result

    def test_prompt_version_constant(self):
        assert PROMPT_VERSION == "v1"

    def test_output_json_instruction_present(self):
        result = build_prompt({}, "insufficient")
        assert "Output JSON" in result


# ---------------------------------------------------------------------------
# Bias-toward-UNSURE post-processing (DEC-VERDICT-004)
# ---------------------------------------------------------------------------

class TestBiasTowardUnsure:
    def test_short_explanation_downgrades_to_unsure(self):
        v, e, d = _apply_bias_toward_unsure("OK", "ok", None)
        assert v == VERDICT_UNSURE

    def test_adequate_explanation_ok_passes_through(self):
        v, e, d = _apply_bias_toward_unsure("OK", "Session length within normal range.", "none")
        assert v == VERDICT_OK

    def test_off_without_dimension_downgrades_to_unsure(self):
        v, e, d = _apply_bias_toward_unsure("OFF", "Something is off today.", None)
        assert v == VERDICT_UNSURE

    def test_off_without_dimension_string_none_downgrades(self):
        v, e, d = _apply_bias_toward_unsure("OFF", "Something is off today.", "none")
        assert v == VERDICT_UNSURE

    def test_off_with_dimension_passes_through(self):
        v, e, d = _apply_bias_toward_unsure("OFF", "Slower decision time than baseline.", "lethargy")
        assert v == VERDICT_OFF

    def test_unsure_always_passes_through(self):
        v, e, d = _apply_bias_toward_unsure("UNSURE", "Conflicting signals.", "anxiety")
        assert v == VERDICT_UNSURE

    def test_explanation_preserved_on_passthrough(self):
        orig_explanation = "Session significantly shorter than 21-day baseline."
        v, e, d = _apply_bias_toward_unsure("OFF", orig_explanation, "lethargy")
        assert e == orig_explanation


# ---------------------------------------------------------------------------
# CLP feature extraction
# ---------------------------------------------------------------------------

class TestClpFeatures:
    @pytest.mark.asyncio
    async def test_no_signal_when_today_and_yesterday_empty(self, state):
        features = await compute_today_features(state, _PATIENT_ID, _TODAY)
        assert features == {"no_signal": True}

    @pytest.mark.asyncio
    async def test_features_extracted_from_session_end(self, state):
        await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
        features = await compute_today_features(state, _PATIENT_ID, _TODAY)
        assert features["total_sessions"] == 1
        assert features["total_duration_ms"] == 300_000
        assert features["error_rate"] == pytest.approx(3 / 60, rel=1e-3)
        assert features["undo_density"] == pytest.approx(2 / 60, rel=1e-3)
        assert features["wins"] == 1

    @pytest.mark.asyncio
    async def test_no_signal_requires_both_days_empty(self, state):
        """Yesterday has a session → today's absence is NOT no_signal."""
        await _seed_session(state, f"{_YESTERDAY.isoformat()}T20:00:00")
        features = await compute_today_features(state, _PATIENT_ID, _TODAY)
        # Should return today features (all zeros except total_sessions=0)
        assert "no_signal" not in features
        assert features["total_sessions"] == 0

    @pytest.mark.asyncio
    async def test_baseline_insufficient_below_min_days(self, state):
        # Seed only 5 days — below min_days=14
        for i in range(5):
            d = _TODAY - timedelta(days=i + 1)
            await _seed_session(state, f"{d.isoformat()}T20:00:00")
        result = await compute_baseline(state, _PATIENT_ID, _TODAY)
        assert result == "insufficient"

    @pytest.mark.asyncio
    async def test_baseline_sufficient_above_min_days(self, state):
        # Seed 15 days of sessions (> min_days=14)
        for i in range(15):
            d = _TODAY - timedelta(days=i + 1)
            await _seed_session(state, f"{d.isoformat()}T20:00:00")
        result = await compute_baseline(state, _PATIENT_ID, _TODAY)
        assert isinstance(result, dict)
        assert "avg_decision_time_ms_mean" in result
        assert result["days_in_window"] == 15

    @pytest.mark.asyncio
    async def test_baseline_excludes_target_date(self, state):
        """Sessions on the verdict date itself must NOT appear in the baseline."""
        # Seed today and 15 prior days
        await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
        for i in range(15):
            d = _TODAY - timedelta(days=i + 1)
            await _seed_session(state, f"{d.isoformat()}T20:00:00")
        result = await compute_baseline(state, _PATIENT_ID, _TODAY)
        assert isinstance(result, dict)
        assert result["days_in_window"] == 15  # today excluded


# ---------------------------------------------------------------------------
# Generator — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_verdict_ok_persisted(state):
    """Successful LLM call → verdict persisted with all fields."""
    await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
    llm = _make_llm({"verdict": "OK", "explanation": "Session within normal range.", "dimension": "none"})

    dv = await generate_verdict_for_date(state, llm, _PATIENT_ID, _TODAY)

    assert dv.verdict == VERDICT_OK
    assert dv.patient_id == _PATIENT_ID
    assert dv.verdict_date == _TODAY.isoformat()
    assert dv.prompt_version == PROMPT_VERSION
    assert dv.model_used == "claude-test"
    assert dv.id is not None
    assert isinstance(dv.telemetry_summary, dict)

    # Verify DB persistence
    row = await state.get_daily_verdict(_PATIENT_ID, _TODAY.isoformat())
    assert row is not None
    assert row["verdict"] == VERDICT_OK


@pytest.mark.asyncio
async def test_generate_verdict_idempotent(state):
    """Calling generate twice for same date returns the same row (single DB row)."""
    await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
    llm = _make_llm()

    dv1 = await generate_verdict_for_date(state, llm, _PATIENT_ID, _TODAY)
    dv2 = await generate_verdict_for_date(state, llm, _PATIENT_ID, _TODAY)

    assert dv1.verdict == dv2.verdict
    assert dv1.verdict_date == dv2.verdict_date
    # LLM was called exactly once (second call hit cache)
    # We can't directly inspect call count via the mock, but we can verify
    # a single row exists via the unique constraint behavior.
    rows = await state.list_verdicts_for_calibration(_PATIENT_ID)
    day_rows = [r for r in rows if r["verdict_date"] == _TODAY.isoformat()]
    assert len(day_rows) == 1


@pytest.mark.asyncio
async def test_no_signal_short_circuit_no_llm_call(state):
    """Zero sessions today + yesterday → NO_SIGNAL without LLM call."""
    call_count = 0

    async def _complete_should_not_be_called(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        raise AssertionError("LLM should not be called for NO_SIGNAL")

    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.complete = _complete_should_not_be_called

    dv = await generate_verdict_for_date(state, mock_llm, _PATIENT_ID, _TODAY)

    assert dv.verdict == VERDICT_NO_SIGNAL
    assert call_count == 0
    assert dv.id is not None


@pytest.mark.asyncio
async def test_insufficient_baseline_stored_in_row(state):
    """When baseline is insufficient, the DB row stores 'insufficient'."""
    # Seed only today (< 14 baseline days)
    await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
    llm = _make_llm({"verdict": "UNSURE", "explanation": "No baseline to compare against.", "dimension": "none"})

    dv = await generate_verdict_for_date(state, llm, _PATIENT_ID, _TODAY)

    assert dv.baseline_summary == "insufficient"
    row = await state.get_daily_verdict(_PATIENT_ID, _TODAY.isoformat())
    assert row["baseline_summary"] == "insufficient"


# ---------------------------------------------------------------------------
# Generator — failure modes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_failure_3x_produces_synthetic_unsure(state):
    """All 3 LLM attempts fail → synthetic UNSURE verdict persisted (DEC-VERDICT-003)."""
    await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
    # fail_count=3 means all 3 attempts fail
    llm = _make_llm(fail_count=3)

    dv = await generate_verdict_for_date(state, llm, _PATIENT_ID, _TODAY)

    assert dv.verdict == VERDICT_UNSURE
    assert "check in" in dv.explanation.lower()
    assert dv.id is not None  # Row was persisted despite failure

    row = await state.get_daily_verdict(_PATIENT_ID, _TODAY.isoformat())
    assert row is not None
    assert row["verdict"] == VERDICT_UNSURE


@pytest.mark.asyncio
async def test_llm_failure_2x_then_success(state):
    """Two failures then success → verdict from the 3rd attempt is used."""
    await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
    llm = _make_llm(
        {"verdict": "OK", "explanation": "Normal session on third attempt.", "dimension": "none"},
        fail_count=2,
    )

    dv = await generate_verdict_for_date(state, llm, _PATIENT_ID, _TODAY)
    assert dv.verdict == VERDICT_OK


@pytest.mark.asyncio
async def test_bias_toward_unsure_off_no_dimension_in_generator(state):
    """OFF with dimension=None in LLM response → UNSURE in persisted row (DEC-VERDICT-004)."""
    await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
    llm = _make_llm({"verdict": "OFF", "explanation": "Something seems different today.", "dimension": "none"})

    dv = await generate_verdict_for_date(state, llm, _PATIENT_ID, _TODAY)

    assert dv.verdict == VERDICT_UNSURE  # downgraded


# ---------------------------------------------------------------------------
# StateManager — labeling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_label_verdict_updates_row(state):
    """label_daily_verdict() correctly sets labeled_truth and labeled_by."""
    await _seed_session(state, f"{_TODAY.isoformat()}T20:00:00")
    llm = _make_llm()
    dv = await generate_verdict_for_date(state, llm, _PATIENT_ID, _TODAY)

    assert dv.id is not None
    await state.label_daily_verdict(dv.id, "TRUTH_OK", "founder@example.com")

    row = await state.get_daily_verdict(_PATIENT_ID, _TODAY.isoformat())
    assert row["labeled_truth"] == "TRUTH_OK"
    assert row["labeled_by"] == "founder@example.com"
    assert row["labeled_at"] is not None


@pytest.mark.asyncio
async def test_unlabeled_verdicts_filtered(state):
    """list_unlabeled_verdicts() only returns rows where labeled_truth IS NULL."""
    # Generate two days of verdicts
    day1 = _TODAY
    day2 = _TODAY - timedelta(days=1)
    await _seed_session(state, f"{day1.isoformat()}T20:00:00")
    await _seed_session(state, f"{day2.isoformat()}T20:00:00")

    llm = _make_llm()
    dv1 = await generate_verdict_for_date(state, llm, _PATIENT_ID, day1)
    dv2 = await generate_verdict_for_date(state, llm, _PATIENT_ID, day2)

    # Label dv2 only
    await state.label_daily_verdict(dv2.id, "TRUTH_OK", "founder")

    unlabeled = await state.list_unlabeled_verdicts(_PATIENT_ID)
    unlabeled_dates = [r["verdict_date"] for r in unlabeled]
    assert day1.isoformat() in unlabeled_dates
    assert day2.isoformat() not in unlabeled_dates
