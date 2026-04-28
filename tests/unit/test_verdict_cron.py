"""
Unit tests for VerdictCron — Phase 15+ M3.

Coverage:
  1. _seconds_until_next_firing: now BEFORE HH:MM today → fires today
  2. _seconds_until_next_firing: now AFTER HH:MM today → fires tomorrow
  3. DST transition (America/New_York spring-forward) → valid future firing
  4. start() with nightly_cron_enabled=False → no task created; stop() is safe
  5. _run_once() with 2 patients: first raises, second succeeds → resilience
  6. _run_once() skips patient with zero recent game sessions

All tests use real StateManager (in-memory SQLite) per DEC-TEST-005.
LLM provider is mocked at the boundary.
No freezegun — injected-now parameter used for schedule tests.

@decision DEC-TEST-006
@title VerdictCron unit tests use injected-now, not freezegun
@status accepted
@rationale _seconds_until_next_firing accepts an optional `now` parameter
    explicitly for testability. This avoids a freezegun dependency and makes
    the DST test deterministic without system-clock manipulation.
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from ada.core.config import AdaConfig, VerdictConfig
from ada.core.events import EventTypes
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.verdict.cron import VerdictCron
from ada.verdict.models import VERDICT_OK, DailyVerdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATIENT_A = "pat-cron-unit-001"
_PATIENT_B = "pat-cron-unit-002"
_UTC = ZoneInfo("UTC")
_NY = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    """In-memory StateManager with two seeded patients."""
    sm = StateManager(":memory:")
    await sm.initialize()
    for pid, name in [(_PATIENT_A, "Alpha"), (_PATIENT_B, "Beta")]:
        await sm.create_patient({
            "id": pid,
            "name": name,
            "dob": None,
            "preferences": {},
            "emergency_contact": None,
            "caregiver_id": None,
        })
    yield sm
    await sm.close()


def _make_config(*, enabled: bool = True, hour: int = 22, minute: int = 30,
                 timezone: str = "UTC") -> AdaConfig:
    """Build an AdaConfig with custom VerdictConfig values."""
    config = AdaConfig()
    config.verdict = VerdictConfig(
        nightly_cron_enabled=enabled,
        cron_hour=hour,
        cron_minute=minute,
        cron_timezone=timezone,
    )
    return config


def _make_llm(
    response_json: dict | None = None,
    *,
    fail: bool = False,
) -> LLMProvider:
    """
    Create a mock LLMProvider.

    # @mock-exempt: LLMProvider.complete() is an external HTTP boundary
    # (Anthropic API). Stubbing it follows DEC-TEST-005 — real HTTP calls
    # are flaky and expensive in CI.
    """
    if response_json is None:
        response_json = {
            "verdict": "OK",
            "explanation": "Session length and decision time within normal range.",
            "dimension": "none",
        }

    async def _complete(messages, **kwargs) -> LLMResponse:
        if fail:
            raise RuntimeError("Simulated LLM failure")
        return LLMResponse(
            content=json.dumps(response_json),
            model="claude-test",
            input_tokens=100,
            output_tokens=50,
        )

    mock = MagicMock(spec=LLMProvider)
    mock.complete = _complete
    return mock


async def _seed_session(
    state: StateManager,
    patient_id: str,
    occurred_at: str,
) -> None:
    """Insert a GAME_SESSION_END event for a patient."""
    await state.create_game_session_event({
        "patient_id": patient_id,
        "event_type": EventTypes.GAME_SESSION_END,
        "payload": {
            "game_session_id": f"gs-{patient_id}-{occurred_at}",
            "duration_ms": 300_000,
            "completed_hands": 1,
            "error_count": 2,
            "end_reason": "completed",
            "deck": "corgi",
            "total_moves": 60,
            "total_undo_count": 1,
            "total_invalid_click_count": 1,
            "total_idle_ms": 10_000,
            "restart_count_today": 0,
        },
        "occurred_at": occurred_at,
    })


def _make_cron(
    config: AdaConfig,
    state: StateManager,
    generator=None,
    llm=None,
) -> VerdictCron:
    """Construct a VerdictCron with sensible test defaults."""
    if generator is None:
        # Default no-op generator
        async def _noop(sm, llm_p, patient_id, verdict_date):
            return DailyVerdict(
                patient_id=patient_id,
                verdict_date=verdict_date.isoformat(),
                verdict=VERDICT_OK,
                explanation="Test verdict.",
                dimension=None,
                model_used="test",
                prompt_version="v1",
                telemetry_summary={},
                baseline_summary="insufficient",
                generated_at="2026-04-28T00:00:00",
            )
        generator = _noop
    if llm is None:
        llm = _make_llm()
    return VerdictCron(config=config, state=state, generator=generator, llm=llm)


# ---------------------------------------------------------------------------
# 1. _seconds_until_next_firing: now BEFORE HH:MM today
# ---------------------------------------------------------------------------

class TestSecondsUntilNextFiring:
    def test_before_firing_time_fires_today(self):
        """now at 21:00 UTC, cron at 22:30 → ~5400 s until today's firing."""
        config = _make_config(hour=22, minute=30, timezone="UTC")
        state = MagicMock()
        cron = VerdictCron(config=config, state=state, generator=None, llm=None)

        now = datetime(2026, 4, 28, 21, 0, 0, tzinfo=_UTC)
        seconds = cron._seconds_until_next_firing(now=now)

        # 22:30 - 21:00 = 90 minutes = 5400 seconds
        assert abs(seconds - 5400.0) < 1.0

    def test_after_firing_time_fires_tomorrow(self):
        """now at 23:00 UTC, cron at 22:30 → ~23.5 h until tomorrow's firing."""
        config = _make_config(hour=22, minute=30, timezone="UTC")
        state = MagicMock()
        cron = VerdictCron(config=config, state=state, generator=None, llm=None)

        now = datetime(2026, 4, 28, 23, 0, 0, tzinfo=_UTC)
        seconds = cron._seconds_until_next_firing(now=now)

        # Tomorrow 22:30 - today 23:00 = 23h30m = 84600 seconds
        assert abs(seconds - 84_600.0) < 1.0

    def test_exactly_at_firing_time_fires_tomorrow(self):
        """now exactly at cron time (22:30:00) → fires tomorrow (0-second delta
        means the condition `now < today_firing` is False)."""
        config = _make_config(hour=22, minute=30, timezone="UTC")
        state = MagicMock()
        cron = VerdictCron(config=config, state=state, generator=None, llm=None)

        now = datetime(2026, 4, 28, 22, 30, 0, tzinfo=_UTC)
        seconds = cron._seconds_until_next_firing(now=now)

        # Exactly 24 hours
        assert abs(seconds - 86_400.0) < 1.0

    def test_dst_spring_forward_new_york(self):
        """DST test: America/New_York spring-forward 2026-03-08 02:00→03:00.

        Cron is set at 22:30 ET. On the night of 2026-03-07 (just before DST
        transition), `now` is 21:00 ET. The cron should resolve a valid future
        firing 90 minutes away without error (and certainly > 0 seconds).
        """
        config = _make_config(hour=22, minute=30, timezone="America/New_York")
        state = MagicMock()
        cron = VerdictCron(config=config, state=state, generator=None, llm=None)

        # Night before spring-forward, 21:00 ET (still standard time)
        now = datetime(2026, 3, 7, 21, 0, 0, tzinfo=_NY)
        seconds = cron._seconds_until_next_firing(now=now)

        # Must be positive and reasonable (< 2 days)
        assert seconds > 0.0
        assert seconds < 2 * 86_400


# ---------------------------------------------------------------------------
# 4. start() disabled → no task; stop() safe no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_disabled_no_task(state):
    """nightly_cron_enabled=False → start() does not create a background task."""
    config = _make_config(enabled=False)
    cron = _make_cron(config, state)

    cron.start()
    assert cron._task is None

    # stop() must be safe even when no task was started
    await cron.stop()
    assert cron._task is None


@pytest.mark.asyncio
async def test_start_enabled_creates_task(state):
    """nightly_cron_enabled=True → start() creates a background asyncio.Task."""
    config = _make_config(enabled=True)
    cron = _make_cron(config, state)

    cron.start()
    assert cron._task is not None
    assert not cron._task.done()

    await cron.stop()
    assert cron._task is None


# ---------------------------------------------------------------------------
# 5. _run_once() resilience: first patient raises, second succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_first_patient_raises_second_succeeds(state):
    """One patient's generator failure must not abort the second patient."""
    today = datetime.now(_UTC).date()
    today_str = today.isoformat()

    # Both patients have recent sessions
    now_str = f"{today_str}T20:00:00"
    await _seed_session(state, _PATIENT_A, now_str)
    await _seed_session(state, _PATIENT_B, now_str)

    call_log: list[str] = []

    async def _flaky_generator(sm, llm_p, patient_id, verdict_date):
        call_log.append(patient_id)
        if patient_id == _PATIENT_A:
            raise RuntimeError("Simulated generator failure for patient A")
        # Patient B succeeds — write a real row so we can assert it
        from ada.verdict.generator import generate_verdict_for_date
        return await generate_verdict_for_date(sm, llm_p, patient_id, verdict_date)

    config = _make_config()
    llm = _make_llm()
    cron = _make_cron(config, state, generator=_flaky_generator, llm=llm)

    await cron._run_once()

    # Both patients were attempted
    assert _PATIENT_A in call_log
    assert _PATIENT_B in call_log

    # Patient B's verdict was written
    row = await state.get_daily_verdict(_PATIENT_B, today_str)
    assert row is not None

    # Patient A has no verdict row (generator raised before persisting)
    row_a = await state.get_daily_verdict(_PATIENT_A, today_str)
    assert row_a is None


# ---------------------------------------------------------------------------
# 6. _run_once() skips patient with no recent sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_skips_patient_with_no_recent_sessions(state):
    """Patient with zero recent game sessions must not trigger generator."""
    today = datetime.now(_UTC).date()
    today_str = today.isoformat()

    # Only patient B has a recent session
    now_str = f"{today_str}T20:00:00"
    await _seed_session(state, _PATIENT_B, now_str)

    generator_calls: list[str] = []

    async def _tracking_generator(sm, llm_p, patient_id, verdict_date):
        generator_calls.append(patient_id)
        # Return a minimal verdict without hitting LLM
        return DailyVerdict(
            patient_id=patient_id,
            verdict_date=verdict_date.isoformat(),
            verdict=VERDICT_OK,
            explanation="Test skip verdict.",
            dimension=None,
            model_used="test",
            prompt_version="v1",
            telemetry_summary={},
            baseline_summary="insufficient",
            generated_at="2026-04-28T00:00:00",
        )

    config = _make_config()
    cron = _make_cron(config, state, generator=_tracking_generator)

    await cron._run_once()

    # Generator was NOT called for patient A (no recent sessions)
    assert _PATIENT_A not in generator_calls
    # Generator WAS called for patient B
    assert _PATIENT_B in generator_calls

    # No verdict row for patient A
    row_a = await state.get_daily_verdict(_PATIENT_A, today_str)
    assert row_a is None
