"""
Integration tests for VerdictCron — Phase 15+ M3.

Tests the full vertical slice: VerdictCron._run_once() → generate_verdict_for_date()
→ StateManager.upsert_daily_verdict() → DB row readable.

Uses real in-memory SQLite StateManager. LLM mocked at boundary (DEC-TEST-005).
No freezegun — _run_once() uses datetime.now() internally for today's date, so
we seed data for today's actual date and verify the row was created.

@decision DEC-TEST-007
@title Integration tests call _run_once() directly to avoid real sleep
@status accepted
@rationale The full loop sleeps until 22:30 which is impractical in CI.
    _run_once() is the unit of work; calling it directly with a seeded DB
    is the correct integration boundary. Fake-clock for the sleep path is
    tested via _seconds_until_next_firing in unit tests.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from ada.core.config import AdaConfig, VerdictConfig
from ada.core.events import EventTypes
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.verdict.cron import VerdictCron
from ada.verdict.generator import generate_verdict_for_date

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATIENT_ID = "pat-cron-int-001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(*, enabled: bool = True) -> AdaConfig:
    config = AdaConfig()
    config.verdict = VerdictConfig(
        nightly_cron_enabled=enabled,
        cron_hour=22,
        cron_minute=30,
        cron_timezone="UTC",
    )
    return config


def _make_llm(response_json: dict | None = None) -> LLMProvider:
    """
    Create a stub LLMProvider.

    # @mock-exempt: LLMProvider.complete() is an external HTTP boundary
    # (Anthropic API). Stubbing it follows DEC-TEST-005.
    """
    if response_json is None:
        response_json = {
            "verdict": "OK",
            "explanation": "Session length within normal range for integration test.",
            "dimension": "none",
        }

    async def _complete(messages, **kwargs) -> LLMResponse:
        return LLMResponse(
            content=json.dumps(response_json),
            model="claude-test",
            input_tokens=100,
            output_tokens=50,
        )

    mock = MagicMock(spec=LLMProvider)
    mock.complete = _complete
    return mock


@pytest_asyncio.fixture
async def state():
    """In-memory StateManager with a seeded patient."""
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": _PATIENT_ID,
        "name": "Integration Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    yield sm
    await sm.close()


async def _seed_today_session(state: StateManager) -> str:
    """Seed a game session for today (UTC). Returns today's ISO date string."""
    today_str = datetime.now(UTC).date().isoformat()
    occurred_at = f"{today_str}T20:00:00"
    await state.create_game_session_event({
        "patient_id": _PATIENT_ID,
        "event_type": EventTypes.GAME_SESSION_END,
        "payload": {
            "game_session_id": f"gs-int-{today_str}",
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
    return today_str


# ---------------------------------------------------------------------------
# Test 1: _run_once fires → verdict row written
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_writes_verdict_row(state):
    """
    _run_once() for a patient with a today session → verdict row in DB.

    This is the primary integration assertion: the cron correctly drives
    generate_verdict_for_date() to completion and the row is readable via
    state.get_daily_verdict().
    """
    today_str = await _seed_today_session(state)

    config = _make_config()
    llm = _make_llm()
    cron = VerdictCron(
        config=config,
        state=state,
        generator=generate_verdict_for_date,
        llm=llm,
    )

    await cron._run_once()

    row = await state.get_daily_verdict(_PATIENT_ID, today_str)
    assert row is not None, f"Expected verdict row for {_PATIENT_ID} / {today_str}"
    assert row["verdict"] in {"OK", "OFF", "UNSURE", "NO_SIGNAL"}
    assert row["patient_id"] == _PATIENT_ID
    assert row["verdict_date"] == today_str


# ---------------------------------------------------------------------------
# Test 2: Idempotency — two _run_once() calls produce exactly one row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_once_idempotent(state):
    """
    Calling _run_once() twice in the same simulated day produces exactly one
    verdict row for (patient_id, today). The second call hits the idempotency
    guard in generate_verdict_for_date() and returns the existing row without
    inserting a new one.
    """
    today_str = await _seed_today_session(state)

    config = _make_config()
    llm = _make_llm()
    cron = VerdictCron(
        config=config,
        state=state,
        generator=generate_verdict_for_date,
        llm=llm,
    )

    await cron._run_once()
    await cron._run_once()

    # Exactly one row in daily_verdicts for this patient+date
    rows = await state.list_verdicts_for_calibration(_PATIENT_ID)
    day_rows = [r for r in rows if r["verdict_date"] == today_str]
    assert len(day_rows) == 1, (
        f"Expected exactly 1 verdict row for {today_str}, got {len(day_rows)}"
    )
