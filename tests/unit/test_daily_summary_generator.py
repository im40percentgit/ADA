"""
Unit tests for DailySummaryGenerator.

Tests use a real EventBus, AsyncMock for state/llm boundaries, and a short
debounce delay (0.1s) so tests don't wait 30 minutes.

# @mock-exempt: StateManager wraps aiosqlite (external DB I/O boundary).
# @mock-exempt: LLMProvider wraps an external HTTP API (Anthropic/OpenAI).
# Both are legitimate external boundaries per Sacred Practice #5. The real
# implementations require live connections or disk that unit tests must not
# depend on. Integration tests in test_daily_summary_flow.py use real SQLite.

@decision DEC-DAILY-004
@title Unit tests mock only external boundaries (DB + LLM)
@status accepted
@rationale StateManager is a thin async wrapper around aiosqlite — real
    integration requires disk or :memory: setup that belongs in integration
    tests. LLMProvider calls an external HTTP API. Mocking both is consistent
    with all other unit tests in this suite (test_session_summarizer.py,
    test_wellness_companion.py). EventBus is NOT mocked — it runs real async
    dispatch so the subscription/publish wiring is genuinely exercised.

Coverage:
 1. Constructor subscribes to SESSION_ENDED
 2. First SESSION_ENDED creates debounce timer for patient
 3. Second SESSION_ENDED for same patient cancels + recreates timer
 4. Timer fires after delay → calls _generate_daily_summary
 5. Timer cancelled (CancelledError) → no summary generated
 6. Generate: aggregates SOAP notes from last 24h
 7. Generate: includes 7-day assessment scores for trend context
 8. Generate: includes fused emotion data from last 24h
 9. Generate: LLM called with correct system + user prompt
10. Generate: successful JSON parse → persist + publish event
11. Generate: malformed JSON → log warning, no persist
12. Generate: UPSERT updates existing same-day summary (idempotency)
13. Shutdown: cancels all pending tasks
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from ada.agents.daily_summary_generator import (
    DailySummaryGenerator,
    _parse_daily_summary_response,
)
from ada.core.bus import EventBus
from ada.core.events import DailySummaryGeneratedEvent, EventTypes, SessionEndedEvent
from ada.llm.base import LLMResponse

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SHORT_DEBOUNCE = 0.1  # seconds — keeps tests fast


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def mock_state() -> AsyncMock:
    """AsyncMock for StateManager — external DB boundary."""  # @mock-exempt: DB
    state = AsyncMock()
    state.get_session_summaries_for_patient.return_value = []
    state.get_assessments.return_value = []
    state.get_crisis_alerts.return_value = []
    state.get_fused_emotions_for_patient.return_value = []
    state.create_or_update_daily_summary.return_value = None
    return state


@pytest.fixture
def mock_llm() -> AsyncMock:
    """AsyncMock for LLMProvider — external HTTP API boundary."""  # @mock-exempt: LLM API
    llm = AsyncMock()
    llm.complete.return_value = LLMResponse(
        content=json.dumps({
            "narrative": "Today was a calm day.",
            "trend_alerts": [],
            "appointment_prep": [],
            "key_topics": ["mood", "sleep"],
            "overall_mood": "stable",
        }),
        model="mock-model",
        input_tokens=100,
        output_tokens=50,
    )
    return llm


def _make_session_ended(patient_id: str = "patient-001") -> SessionEndedEvent:
    return SessionEndedEvent(
        source="test",
        session_id="session-001",
        patient_id=patient_id,
    )


# ---------------------------------------------------------------------------
# Test 1: Constructor subscribes to SESSION_ENDED
# ---------------------------------------------------------------------------

def test_constructor_subscribes_to_session_ended(bus, mock_state, mock_llm):
    """DailySummaryGenerator subscribes to SESSION_ENDED on construction."""
    DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)
    subscribers = bus._subscribers.get(EventTypes.SESSION_ENDED, [])
    # EventBus stores (subscriber_name, queue) tuples — name is index 0
    subscriber_names = [s[0] for s in subscribers]
    assert "daily_summary_generator" in subscriber_names


# ---------------------------------------------------------------------------
# Test 2: First SESSION_ENDED creates debounce timer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_session_ended_creates_timer(bus, mock_state, mock_llm):
    """First SESSION_ENDED creates an asyncio.Task in _pending."""
    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)
    assert len(generator._pending) == 0

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(0)

    assert "patient-001" in generator._pending
    assert not generator._pending["patient-001"].done()

    await generator.shutdown()
    await bus.stop()


# ---------------------------------------------------------------------------
# Test 3: Second SESSION_ENDED cancels + recreates timer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_session_ended_resets_timer(bus, mock_state, mock_llm):
    """Second SESSION_ENDED for same patient cancels existing task and creates a new one."""
    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=10.0)

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(0)

    first_task = generator._pending.get("patient-001")
    assert first_task is not None

    await bus.publish(_make_session_ended("patient-001"))
    # Give cancellation time to propagate through the event loop
    await asyncio.sleep(0.05)

    second_task = generator._pending.get("patient-001")
    assert second_task is not None
    assert second_task is not first_task
    # Task is either cancelled or done after cancellation propagates
    assert first_task.cancelled() or first_task.done()

    await generator.shutdown()
    await bus.stop()


# ---------------------------------------------------------------------------
# Test 4: Timer fires after delay → _generate_daily_summary called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timer_fires_and_calls_generate(bus, mock_state, mock_llm):
    """After the debounce delay, _generate_daily_summary is called."""
    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(SHORT_DEBOUNCE + 0.15)

    mock_state.get_session_summaries_for_patient.assert_called_once()
    mock_state.get_assessments.assert_called_once()

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 5: Cancelled timer → no summary generated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancelled_timer_no_summary(bus, mock_state, mock_llm):
    """Cancelling the timer before it fires produces no summary."""
    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=10.0)

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(0)

    task = generator._pending["patient-001"]
    task.cancel()
    await asyncio.sleep(0.05)

    mock_state.create_or_update_daily_summary.assert_not_called()
    mock_llm.complete.assert_not_called()

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 6: Generate aggregates SOAP notes from last 24h
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_queries_soap_notes_with_since(bus, mock_state, mock_llm):
    """_generate_daily_summary calls get_session_summaries_for_patient with a since timestamp."""
    mock_state.get_session_summaries_for_patient.return_value = [
        {
            "id": "ss-001",
            "session_id": "sess-001",
            "patient_id": "patient-001",
            "subjective": "Felt anxious",
            "objective": "Spoke quickly",
            "assessment": "Elevated anxiety",
            "plan": "Continue check-ins",
            "key_topics": ["anxiety"],
            "risk_flags": [],
        }
    ]

    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(SHORT_DEBOUNCE + 0.15)

    call_args = mock_state.get_session_summaries_for_patient.call_args
    assert call_args[0][0] == "patient-001"
    # second positional arg or keyword 'since'
    since_arg = call_args[1].get("since") if call_args[1] else call_args[0][1]
    assert isinstance(since_arg, str) and len(since_arg) > 0

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 7: Generate includes 7-day assessment scores
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_queries_assessments_for_trend(bus, mock_state, mock_llm):
    """_generate_daily_summary calls get_assessments for trend context."""
    mock_state.get_assessments.return_value = [
        {"instrument": "phq9", "total_score": 12, "severity": "moderate", "timestamp": "2026-03-21T10:00:00"},
        {"instrument": "phq9", "total_score": 10, "severity": "moderate", "timestamp": "2026-03-15T10:00:00"},
    ]

    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(SHORT_DEBOUNCE + 0.15)

    mock_state.get_assessments.assert_called_once_with("patient-001")

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 8: Generate includes fused emotion data from last 24h
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_queries_fused_emotions(bus, mock_state, mock_llm):
    """_generate_daily_summary calls get_fused_emotions_for_patient with since timestamp."""
    mock_state.get_fused_emotions_for_patient.return_value = [
        {
            "id": "fe-001",
            "fused_emotion": "anxious",
            "fused_valence": -0.4,
            "fused_arousal": 0.7,
            "modalities_available": ["text", "voice"],
        }
    ]

    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(SHORT_DEBOUNCE + 0.15)

    call_args = mock_state.get_fused_emotions_for_patient.call_args
    assert call_args[0][0] == "patient-001"
    since_arg = call_args[1].get("since") if call_args[1] else call_args[0][1]
    assert isinstance(since_arg, str) and len(since_arg) > 0

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 9: LLM called with correct system + user prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_calls_llm_with_correct_prompts(bus, mock_state, mock_llm):
    """LLM is called with the daily summary system prompt and a structured user prompt."""
    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(SHORT_DEBOUNCE + 0.15)

    mock_llm.complete.assert_called_once()
    call_kwargs = mock_llm.complete.call_args[1]

    # System prompt must mention caregiver context
    assert "caregiver" in call_kwargs["system"].lower()
    # Messages must be a single user turn
    messages = call_kwargs.get("messages") or mock_llm.complete.call_args[0][0]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "Today's date" in messages[0]["content"]

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 10: Successful JSON parse → persist + publish event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_success_persists_and_publishes(bus, mock_state, mock_llm):
    """Valid JSON response triggers persist and DAILY_SUMMARY_GENERATED event."""
    published_events: list = []
    await bus.start()

    async def capture(event):
        published_events.append(event)

    bus.subscribe(EventTypes.DAILY_SUMMARY_GENERATED, capture, "test_capture")

    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(SHORT_DEBOUNCE + 0.2)

    mock_state.create_or_update_daily_summary.assert_called_once()
    record = mock_state.create_or_update_daily_summary.call_args[0][0]
    assert record["patient_id"] == "patient-001"
    assert record["narrative"] == "Today was a calm day."
    assert record["overall_mood"] == "stable"

    assert len(published_events) == 1
    assert isinstance(published_events[0], DailySummaryGeneratedEvent)
    assert published_events[0].patient_id == "patient-001"

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 11: Malformed JSON → log warning, no persist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_malformed_json_no_persist(bus, mock_state, mock_llm):
    """Malformed LLM JSON response logs a warning and skips persistence."""
    mock_llm.complete.return_value = LLMResponse(
        content="This is not JSON at all.",
        model="mock-model",
        input_tokens=10,
        output_tokens=5,
    )

    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)

    await bus.start()
    with patch("ada.agents.daily_summary_generator.logger") as mock_logger:
        await bus.publish(_make_session_ended("patient-001"))
        await asyncio.sleep(SHORT_DEBOUNCE + 0.2)
        mock_logger.warning.assert_called()

    mock_state.create_or_update_daily_summary.assert_not_called()

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 12: UPSERT — second generation same day replaces existing record
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_upsert_same_day(bus, mock_state, mock_llm):
    """Two generations on the same date both call create_or_update_daily_summary (UPSERT)."""
    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=SHORT_DEBOUNCE)

    await bus.start()

    # First generation
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(SHORT_DEBOUNCE + 0.2)

    # Second generation (simulates late-day session after debounce already fired)
    await bus.publish(_make_session_ended("patient-001"))
    await asyncio.sleep(SHORT_DEBOUNCE + 0.2)

    assert mock_state.create_or_update_daily_summary.call_count == 2
    dates = [
        mock_state.create_or_update_daily_summary.call_args_list[i][0][0]["summary_date"]
        for i in range(2)
    ]
    assert dates[0] == dates[1]

    await bus.stop()


# ---------------------------------------------------------------------------
# Test 13: Shutdown cancels all pending tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shutdown_cancels_all_pending_tasks(bus, mock_state, mock_llm):
    """shutdown() cancels all tasks in _pending and clears the dict."""
    generator = DailySummaryGenerator(bus, mock_state, mock_llm, debounce_seconds=60.0)

    await bus.start()
    await bus.publish(_make_session_ended("patient-001"))
    await bus.publish(_make_session_ended("patient-002"))
    await asyncio.sleep(0)

    assert len(generator._pending) == 2
    tasks = list(generator._pending.values())

    await generator.shutdown()
    # Allow the event loop to process the cancellation signals
    await asyncio.sleep(0.05)

    assert len(generator._pending) == 0
    for task in tasks:
        # Task is cancelled or done — both are acceptable settled states
        assert task.cancelled() or task.done()

    await bus.stop()


# ---------------------------------------------------------------------------
# Unit tests for _parse_daily_summary_response helper (pure function — no mocks)
# ---------------------------------------------------------------------------

def test_parse_valid_json():
    """Direct JSON string parses correctly."""
    raw = json.dumps({
        "narrative": "Good day.",
        "trend_alerts": [],
        "appointment_prep": [],
        "key_topics": [],
        "overall_mood": "stable",
    })
    result = _parse_daily_summary_response(raw)
    assert result is not None
    assert result["narrative"] == "Good day."


def test_parse_json_with_markdown_fence():
    """JSON wrapped in ```json ... ``` code fences is stripped and parsed."""
    inner = json.dumps({
        "narrative": "Calm.",
        "trend_alerts": [],
        "appointment_prep": [],
        "key_topics": [],
        "overall_mood": "stable",
    })
    raw = f"```json\n{inner}\n```"
    result = _parse_daily_summary_response(raw)
    assert result is not None
    assert result["narrative"] == "Calm."


def test_parse_invalid_json_returns_none():
    """Completely invalid response returns None without raising."""
    result = _parse_daily_summary_response("not json at all")
    assert result is None
