"""
Unit tests for SessionSummarizer and SOAPNote model.

Coverage:
- SOAPNote model: construction, defaults, field types
- _parse_soap_response: valid JSON, code-fenced JSON, malformed input
- _build_transcript: role mapping, ordering
- SessionSummarizer._on_session_ended:
    - happy path: SESSION_ENDED → LLM called → summary persisted → SESSION_SUMMARIZED published
    - no messages → skipped (no LLM call, no event)
    - LLM failure → skipped gracefully
    - malformed LLM response → skipped gracefully
    - wrong event type → ignored
- StateManager.create_session_summary / get_session_summary: CRUD with list fields

Tests use real in-memory SQLite and real EventBus. No mocks cross module
boundaries — the LLM is stubbed with a minimal concrete LLMProvider subclass.

@decision DEC-SUMMARY-005
@title Unit tests use in-memory SQLite and a minimal LLM stub
@status accepted
@rationale Consistent with DEC-TEST-005: real DB gives actual SQL execution,
    catching constraint violations and JSON round-trip bugs that a mock would
    hide. LLM is the only external boundary — a concrete stub returning canned
    JSON exercises the full parse/persist/publish path.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.session_summarizer import SessionSummarizer, _build_transcript, _parse_soap_response
from ada.core.bus import EventBus
from ada.core.events import EventTypes, SessionEndedEvent, SessionSummarizedEvent
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse
from ada.models.summary import SOAPNote


# ---------------------------------------------------------------------------
# Minimal LLM stub
# ---------------------------------------------------------------------------

class _StubLLM(LLMProvider):
    """Returns a canned response or raises on demand."""

    def __init__(self, response: str = "", raise_exc: Exception | None = None) -> None:
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def complete(self, messages, **kwargs) -> LLMResponse:
        self.calls.append({"messages": messages, **kwargs})
        if self._raise:
            raise self._raise
        return LLMResponse(
            content=self._response,
            model="stub",
            input_tokens=0,
            output_tokens=len(self._response),
        )

    async def stream(self, messages, **kwargs) -> AsyncIterator[str]:
        yield self._response


_VALID_SOAP_JSON = json.dumps({
    "subjective": "Patient reports feeling overwhelmed at work.",
    "objective": "Patient spoke quickly; described 3 stressors in detail.",
    "assessment": "Moderate anxiety with occupational triggers.",
    "plan": "Continue CBT thought records; review at next session.",
    "key_topics": ["work stress", "anxiety"],
    "risk_flags": [],
})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    # Seed patient + session so FK constraints pass
    await sm.create_patient({
        "id": "pat-unit-001",
        "name": "Unit Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({
        "id": "sess-unit-001",
        "patient_id": "pat-unit-001",
    })
    yield sm
    await sm.close()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


# ---------------------------------------------------------------------------
# SOAPNote model tests
# ---------------------------------------------------------------------------

class TestSOAPNote:

    def test_required_fields(self):
        note = SOAPNote(
            subjective="I feel sad.",
            objective="Flat affect noted.",
            assessment="Depressed mood.",
            plan="Weekly sessions.",
        )
        assert note.subjective == "I feel sad."
        assert note.objective == "Flat affect noted."
        assert note.assessment == "Depressed mood."
        assert note.plan == "Weekly sessions."

    def test_default_list_fields_are_empty(self):
        note = SOAPNote(
            subjective="s", objective="o", assessment="a", plan="p"
        )
        assert note.key_topics == []
        assert note.risk_flags == []

    def test_default_ids_are_empty_strings(self):
        note = SOAPNote(
            subjective="s", objective="o", assessment="a", plan="p"
        )
        assert note.session_id == ""
        assert note.patient_id == ""

    def test_created_at_defaults_to_utcnow(self):
        before = datetime.utcnow()
        note = SOAPNote(
            subjective="s", objective="o", assessment="a", plan="p"
        )
        after = datetime.utcnow()
        assert before <= note.created_at <= after

    def test_key_topics_accepts_list(self):
        note = SOAPNote(
            subjective="s", objective="o", assessment="a", plan="p",
            key_topics=["anxiety", "work stress"],
        )
        assert note.key_topics == ["anxiety", "work stress"]

    def test_risk_flags_accepts_list(self):
        note = SOAPNote(
            subjective="s", objective="o", assessment="a", plan="p",
            risk_flags=["passive suicidal ideation"],
        )
        assert note.risk_flags == ["passive suicidal ideation"]

    def test_session_and_patient_ids_set(self):
        note = SOAPNote(
            subjective="s", objective="o", assessment="a", plan="p",
            session_id="sess-001", patient_id="pat-001",
        )
        assert note.session_id == "sess-001"
        assert note.patient_id == "pat-001"


# ---------------------------------------------------------------------------
# _parse_soap_response tests
# ---------------------------------------------------------------------------

class TestParseSoapResponse:

    def test_valid_json_parsed(self):
        result = _parse_soap_response(_VALID_SOAP_JSON)
        assert result is not None
        assert result["subjective"] == "Patient reports feeling overwhelmed at work."
        assert result["key_topics"] == ["work stress", "anxiety"]
        assert result["risk_flags"] == []

    def test_code_fenced_json_parsed(self):
        fenced = f"```json\n{_VALID_SOAP_JSON}\n```"
        result = _parse_soap_response(fenced)
        assert result is not None
        assert result["plan"] == "Continue CBT thought records; review at next session."

    def test_code_fenced_without_language_tag(self):
        fenced = f"```\n{_VALID_SOAP_JSON}\n```"
        result = _parse_soap_response(fenced)
        assert result is not None
        assert "assessment" in result

    def test_malformed_returns_none(self):
        assert _parse_soap_response("not json at all") is None

    def test_partial_json_returns_none(self):
        assert _parse_soap_response('{"subjective": "incomplete"') is None

    def test_empty_string_returns_none(self):
        assert _parse_soap_response("") is None


# ---------------------------------------------------------------------------
# _build_transcript tests
# ---------------------------------------------------------------------------

class TestBuildTranscript:

    def test_user_role_maps_to_patient(self):
        msgs = [{"role": "user", "content": "I feel anxious."}]
        assert _build_transcript(msgs) == "Patient: I feel anxious."

    def test_assistant_role_maps_to_therapist(self):
        msgs = [{"role": "assistant", "content": "Tell me more."}]
        assert _build_transcript(msgs) == "Therapist: Tell me more."

    def test_ordering_preserved(self):
        msgs = [
            {"role": "user", "content": "Hello."},
            {"role": "assistant", "content": "Hi there."},
            {"role": "user", "content": "I struggle with sleep."},
        ]
        transcript = _build_transcript(msgs)
        lines = transcript.split("\n")
        assert lines[0] == "Patient: Hello."
        assert lines[1] == "Therapist: Hi there."
        assert lines[2] == "Patient: I struggle with sleep."

    def test_empty_messages_returns_empty_string(self):
        assert _build_transcript([]) == ""

    def test_unknown_role_maps_to_therapist(self):
        msgs = [{"role": "system", "content": "Context."}]
        assert _build_transcript(msgs) == "Therapist: Context."


# ---------------------------------------------------------------------------
# StateManager CRUD tests
# ---------------------------------------------------------------------------

class TestSessionSummaryCRUD:

    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, state):
        summary = {
            "id": "sum-001",
            "session_id": "sess-unit-001",
            "patient_id": "pat-unit-001",
            "subjective": "Patient reports sadness.",
            "objective": "Tearful throughout session.",
            "assessment": "Moderate depression.",
            "plan": "Increase session frequency.",
            "key_topics": ["depression", "isolation"],
            "risk_flags": [],
        }
        await state.create_session_summary(summary)
        retrieved = await state.get_session_summary("sess-unit-001")
        assert retrieved is not None
        assert retrieved["id"] == "sum-001"
        assert retrieved["subjective"] == "Patient reports sadness."
        assert retrieved["key_topics"] == ["depression", "isolation"]
        assert retrieved["risk_flags"] == []

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, state):
        result = await state.get_session_summary("nonexistent-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_risk_flags_round_trip(self, state):
        summary = {
            "id": "sum-002",
            "session_id": "sess-unit-001",
            "patient_id": "pat-unit-001",
            "subjective": "s", "objective": "o", "assessment": "a", "plan": "p",
            "key_topics": [],
            "risk_flags": ["passive suicidal ideation", "medication non-compliance"],
        }
        await state.create_session_summary(summary)
        retrieved = await state.get_session_summary("sess-unit-001")
        assert retrieved["risk_flags"] == ["passive suicidal ideation", "medication non-compliance"]

    @pytest.mark.asyncio
    async def test_unique_constraint_on_session_id(self, state):
        base = {
            "session_id": "sess-unit-001",
            "patient_id": "pat-unit-001",
            "subjective": "s", "objective": "o", "assessment": "a", "plan": "p",
        }
        await state.create_session_summary({"id": "sum-003", **base})
        with pytest.raises(Exception):
            await state.create_session_summary({"id": "sum-004", **base})


# ---------------------------------------------------------------------------
# SessionSummarizer behaviour tests
# ---------------------------------------------------------------------------

class TestSessionSummarizer:

    @pytest.mark.asyncio
    async def test_happy_path(self, state, bus):
        """SESSION_ENDED with messages → LLM called → summary persisted → event published."""
        await bus.start()
        try:
            # Seed a message in the session
            await state.save_message({
                "id": "msg-001",
                "session_id": "sess-unit-001",
                "role": "user",
                "content": "I feel overwhelmed.",
            })

            llm = _StubLLM(response=_VALID_SOAP_JSON)
            published: list = []
            bus.subscribe(EventTypes.SESSION_SUMMARIZED, lambda e: published.append(e), "test_sub")

            summarizer = SessionSummarizer(bus, state, llm)

            event = SessionEndedEvent(
                session_id="sess-unit-001",
                patient_id="pat-unit-001",
            )
            await summarizer._on_session_ended(event)

            # Give the event loop a tick to process the published event
            await asyncio.sleep(0)

            # LLM was called once
            assert len(llm.calls) == 1

            # Summary persisted
            summary = await state.get_session_summary("sess-unit-001")
            assert summary is not None
            assert summary["subjective"] == "Patient reports feeling overwhelmed at work."
            assert summary["key_topics"] == ["work stress", "anxiety"]
            assert summary["risk_flags"] == []
            assert summary["session_id"] == "sess-unit-001"
            assert summary["patient_id"] == "pat-unit-001"

            # SESSION_SUMMARIZED event published
            assert len(published) == 1
            evt = published[0]
            assert isinstance(evt, SessionSummarizedEvent)
            assert evt.session_id == "sess-unit-001"
            assert evt.patient_id == "pat-unit-001"
            assert evt.summary_id == summary["id"]
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_no_messages_skips(self, state, bus):
        """SESSION_ENDED with no messages → LLM not called, no summary, no event."""
        await bus.start()
        try:
            llm = _StubLLM(response=_VALID_SOAP_JSON)
            published: list = []
            bus.subscribe(EventTypes.SESSION_SUMMARIZED, lambda e: published.append(e), "test_sub")

            summarizer = SessionSummarizer(bus, state, llm)
            event = SessionEndedEvent(
                session_id="sess-unit-001",
                patient_id="pat-unit-001",
            )
            await summarizer._on_session_ended(event)
            await asyncio.sleep(0)

            assert len(llm.calls) == 0
            assert await state.get_session_summary("sess-unit-001") is None
            assert len(published) == 0
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_llm_failure_skips_gracefully(self, state, bus):
        """LLM exception → warning logged, no summary, no event, no crash."""
        await bus.start()
        try:
            await state.save_message({
                "id": "msg-002",
                "session_id": "sess-unit-001",
                "role": "user",
                "content": "Hello.",
            })

            llm = _StubLLM(raise_exc=RuntimeError("LLM timeout"))
            published: list = []
            bus.subscribe(EventTypes.SESSION_SUMMARIZED, lambda e: published.append(e), "test_sub")

            summarizer = SessionSummarizer(bus, state, llm)
            event = SessionEndedEvent(
                session_id="sess-unit-001",
                patient_id="pat-unit-001",
            )
            await summarizer._on_session_ended(event)
            await asyncio.sleep(0)

            assert await state.get_session_summary("sess-unit-001") is None
            assert len(published) == 0
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_malformed_llm_response_skips_gracefully(self, state, bus):
        """Malformed JSON from LLM → warning logged, no summary, no event."""
        await bus.start()
        try:
            await state.save_message({
                "id": "msg-003",
                "session_id": "sess-unit-001",
                "role": "user",
                "content": "Hello.",
            })

            llm = _StubLLM(response="this is not json")
            published: list = []
            bus.subscribe(EventTypes.SESSION_SUMMARIZED, lambda e: published.append(e), "test_sub")

            summarizer = SessionSummarizer(bus, state, llm)
            event = SessionEndedEvent(
                session_id="sess-unit-001",
                patient_id="pat-unit-001",
            )
            await summarizer._on_session_ended(event)
            await asyncio.sleep(0)

            assert await state.get_session_summary("sess-unit-001") is None
            assert len(published) == 0
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_wrong_event_type_ignored(self, state, bus):
        """Non-SessionEndedEvent passed directly → ignored, no LLM call."""
        await bus.start()
        try:
            llm = _StubLLM(response=_VALID_SOAP_JSON)
            summarizer = SessionSummarizer(bus, state, llm)

            from ada.core.events import AdaEvent
            wrong_event = AdaEvent(event_type="some.other.event")
            await summarizer._on_session_ended(wrong_event)
            await asyncio.sleep(0)

            assert len(llm.calls) == 0
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    async def test_subscribes_to_session_ended_on_init(self, state, bus):
        """SessionSummarizer subscribes to SESSION_ENDED at construction time."""
        llm = _StubLLM(response=_VALID_SOAP_JSON)
        summarizer = SessionSummarizer(bus, state, llm)
        # _subscribers[event_type] is a list of (name, queue) tuples
        sub_names = [name for name, _ in bus._subscribers.get(EventTypes.SESSION_ENDED, [])]
        assert "session_summarizer" in sub_names

    @pytest.mark.asyncio
    async def test_fenced_llm_response_parsed(self, state, bus):
        """LLM returns JSON wrapped in code fences → still parsed correctly."""
        await bus.start()
        try:
            await state.save_message({
                "id": "msg-004",
                "session_id": "sess-unit-001",
                "role": "user",
                "content": "I have been anxious.",
            })

            fenced_response = f"```json\n{_VALID_SOAP_JSON}\n```"
            llm = _StubLLM(response=fenced_response)

            summarizer = SessionSummarizer(bus, state, llm)
            event = SessionEndedEvent(
                session_id="sess-unit-001",
                patient_id="pat-unit-001",
            )
            await summarizer._on_session_ended(event)
            await asyncio.sleep(0)

            summary = await state.get_session_summary("sess-unit-001")
            assert summary is not None
            assert summary["assessment"] == "Moderate anxiety with occupational triggers."
        finally:
            await bus.stop()
