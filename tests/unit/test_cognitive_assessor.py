"""
Unit tests for ada.agents.cognitive_assessor.CognitiveAssessorAgent.

Tests run against real in-memory SQLite, real EventBus, and a MockLLMProvider
(genuine LLMProvider subclass). No mocks for internal modules (Sacred Practice #5).

Coverage:
- Agent identity and lifecycle
- Standard instrument mode: PHQ-9 triggered → questions published → answers scored → saved → ASSESSMENT_COMPLETED
- Standard instrument mode: GAD-7 and WHO-5 triggered similarly
- Answer scoring via LLM (natural language → integer)
- LLM scoring failure falls back to 0 gracefully
- Unknown instrument is silently ignored
- MESSAGE_RECEIVED with no active session is a no-op
- Adaptive cognitive screening: ASSESSMENT_TRIGGERED(cognitive) → screening created
  → tasks generated → scored → COGNITIVE_SCREENING_COMPLETED published
- Adaptive screening: LLM failure on task generation degrades gracefully

@decision DEC-ASSESS-002
@title CognitiveAssessorAgent unit tests use real infrastructure, no mocks
@status accepted
@rationale Sacred Practice #5: no internal mocks. MockLLMProvider is a genuine
    LLMProvider subclass with a per-call response queue. StateManager uses
    ":memory:" SQLite. EventBus is fully live.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import pytest

from ada.agents.cognitive_assessor import CognitiveAssessorAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AdaEvent,
    AssessmentCompletedEvent,
    AssessmentTriggeredEvent,
    CognitiveScreeningCompletedEvent,
    CognitiveScreeningStartedEvent,
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """Deterministic LLM stub with a per-call response queue."""

    def __init__(self, default_response: str = "2") -> None:
        self.default_response = default_response
        self.response_queue: list[str] = []
        self.calls: list[dict] = []

    def queue(self, response: str) -> None:
        self.response_queue.append(response)

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system})
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        return LLMResponse(content=content, model="mock", input_tokens=1, output_tokens=1)

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        yield self.default_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "pat-cog-001",
        "name": "Cognitive Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({
        "id": "sess-cog-001",
        "patient_id": "pat-cog-001",
    })
    yield sm
    await sm.close()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def config() -> AdaConfig:
    return AdaConfig()


@pytest.fixture
def llm() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
def agent(bus, config, state, llm) -> CognitiveAssessorAgent:
    a = CognitiveAssessorAgent()
    a.initialize(bus, config, state, llm)
    return a


# ---------------------------------------------------------------------------
# Identity and lifecycle
# ---------------------------------------------------------------------------

class TestAgentIdentity:

    def test_name_is_cognitive_assessor(self, agent):
        assert agent.name == "cognitive_assessor"

    def test_description_is_set(self, agent):
        assert len(agent.description) > 10

    def test_supported_events_includes_assessment_triggered(self, agent):
        assert EventTypes.ASSESSMENT_TRIGGERED in agent.supported_events

    def test_supported_events_includes_message_received(self, agent):
        assert EventTypes.MESSAGE_RECEIVED in agent.supported_events

    async def test_start_and_stop(self, agent, bus):
        await bus.start()
        await agent.start()
        assert agent.is_running
        await agent.stop()
        assert not agent.is_running
        await bus.stop()


# ---------------------------------------------------------------------------
# Standard instrument: PHQ-9
# ---------------------------------------------------------------------------

class TestPHQ9Assessment:

    async def test_phq9_trigger_publishes_first_question(self, agent, bus, llm):
        """ASSESSMENT_TRIGGERED(phq9) should publish the first question."""
        await bus.start()
        await agent.start()

        sent: list[MessageSentEvent] = []

        async def capture(event):
            if isinstance(event, MessageSentEvent):
                sent.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "test-q1")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="phq9",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        assert len(sent) == 1
        assert "PHQ9 Question 1/9" in sent[0].content
        assert sent[0].agent_name == "cognitive_assessor"

        await agent.stop()
        await bus.stop()

    async def test_phq9_answer_advances_to_next_question(self, agent, bus, llm):
        """Answering question 1 should publish question 2."""
        await bus.start()
        await agent.start()

        sent: list[MessageSentEvent] = []

        async def capture(event):
            if isinstance(event, MessageSentEvent):
                sent.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "test-q2")

        # Trigger assessment
        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="phq9",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        # LLM returns score "1" for the answer
        llm.queue("1")

        # Answer question 1
        answer = MessageReceivedEvent(
            source="user",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            content="several days",
            message_id="msg-001",
        )
        await agent.handle_event(answer)
        await asyncio.sleep(0.05)

        # Should now have q1 + q2 published
        assert len(sent) == 2
        assert "Question 2/9" in sent[1].content

        await agent.stop()
        await bus.stop()

    async def test_phq9_all_answers_completes_assessment(self, agent, bus, llm, state):
        """Answering all 9 PHQ-9 items should save to DB and publish ASSESSMENT_COMPLETED."""
        await bus.start()
        await agent.start()

        completed: list[AssessmentCompletedEvent] = []

        async def capture(event):
            if isinstance(event, AssessmentCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, capture, "test-complete")

        # Queue a score of "2" for all 9 items
        for _ in range(9):
            llm.queue("2")

        # Start assessment
        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="phq9",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        # Answer all 9 questions
        for i in range(9):
            answer = MessageReceivedEvent(
                source="user",
                session_id="sess-cog-001",
                patient_id="pat-cog-001",
                content="nearly every day",
                message_id=f"msg-phq-{i}",
            )
            await agent.handle_event(answer)
            await asyncio.sleep(0.05)

        # Check ASSESSMENT_COMPLETED published
        assert len(completed) == 1
        evt = completed[0]
        assert evt.instrument == "phq9"
        assert evt.total_score == 18  # 9 items × 2
        assert evt.severity == "moderately_severe"
        assert evt.patient_id == "pat-cog-001"

        # Check saved to DB
        results = await state.get_assessments("pat-cog-001", instrument="phq9")
        assert len(results) == 1
        assert results[0]["total_score"] == 18
        assert results[0]["severity"] == "moderately_severe"

        # Session cleared from active assessments
        assert "sess-cog-001" not in agent._active_assessments

        await agent.stop()
        await bus.stop()

    async def test_phq9_score_0_gives_minimal_severity(self, agent, bus, llm, state):
        """All zero scores should yield minimal severity."""
        await bus.start()
        await agent.start()

        completed: list[AssessmentCompletedEvent] = []

        async def cap(event):
            if isinstance(event, AssessmentCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, cap, "test-minimal")

        for _ in range(9):
            llm.queue("0")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="phq9",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        for i in range(9):
            answer = MessageReceivedEvent(
                source="user",
                session_id="sess-cog-001",
                patient_id="pat-cog-001",
                content="not at all",
                message_id=f"msg-zero-{i}",
            )
            await agent.handle_event(answer)
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert completed[0].total_score == 0
        assert completed[0].severity == "minimal"

        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Standard instrument: GAD-7
# ---------------------------------------------------------------------------

class TestGAD7Assessment:

    async def test_gad7_trigger_publishes_first_question(self, agent, bus, llm):
        """ASSESSMENT_TRIGGERED(gad7) should publish the first question."""
        await bus.start()
        await agent.start()

        sent: list[MessageSentEvent] = []

        async def capture(event):
            if isinstance(event, MessageSentEvent):
                sent.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "test-gad7-q1")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="gad7",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        assert len(sent) == 1
        assert "GAD7 Question 1/7" in sent[0].content

        await agent.stop()
        await bus.stop()

    async def test_gad7_severe_severity_at_max_score(self, agent, bus, llm, state):
        """All 3s (21/21) should yield severe severity."""
        await bus.start()
        await agent.start()

        completed: list[AssessmentCompletedEvent] = []

        async def cap(event):
            if isinstance(event, AssessmentCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, cap, "test-gad7-severe")

        for _ in range(7):
            llm.queue("3")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="gad7",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        for i in range(7):
            answer = MessageReceivedEvent(
                source="user",
                session_id="sess-cog-001",
                patient_id="pat-cog-001",
                content="nearly every day",
                message_id=f"msg-gad-{i}",
            )
            await agent.handle_event(answer)
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert completed[0].total_score == 21
        assert completed[0].severity == "severe"

        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Standard instrument: WHO-5
# ---------------------------------------------------------------------------

class TestWHO5Assessment:

    async def test_who5_trigger_publishes_first_question(self, agent, bus, llm):
        """ASSESSMENT_TRIGGERED(who5) should publish the first question."""
        await bus.start()
        await agent.start()

        sent: list[MessageSentEvent] = []

        async def capture(event):
            if isinstance(event, MessageSentEvent):
                sent.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "test-who5-q1")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="who5",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        assert len(sent) == 1
        assert "WHO5 Question 1/5" in sent[0].content

        await agent.stop()
        await bus.stop()

    async def test_who5_excellent_severity_at_max(self, agent, bus, llm, state):
        """All 5s (25/25) should yield excellent severity."""
        await bus.start()
        await agent.start()

        completed: list[AssessmentCompletedEvent] = []

        async def cap(event):
            if isinstance(event, AssessmentCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, cap, "test-who5-excellent")

        for _ in range(5):
            llm.queue("5")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="who5",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        for i in range(5):
            answer = MessageReceivedEvent(
                source="user",
                session_id="sess-cog-001",
                patient_id="pat-cog-001",
                content="all of the time",
                message_id=f"msg-who-{i}",
            )
            await agent.handle_event(answer)
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert completed[0].total_score == 25
        assert completed[0].severity == "excellent"

        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    async def test_unknown_instrument_is_ignored(self, agent, bus):
        """An unknown instrument string should be silently ignored."""
        await bus.start()
        await agent.start()

        sent: list[MessageSentEvent] = []

        async def capture(event):
            if isinstance(event, MessageSentEvent):
                sent.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "test-unknown")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="unknown_instrument",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        # Nothing should be published
        assert len(sent) == 0
        assert "sess-cog-001" not in agent._active_assessments

        await agent.stop()
        await bus.stop()

    async def test_message_received_with_no_active_session_is_noop(self, agent, bus):
        """MESSAGE_RECEIVED when no assessment is active should have no side-effects."""
        await bus.start()
        await agent.start()

        sent: list[MessageSentEvent] = []

        async def capture(event):
            if isinstance(event, MessageSentEvent):
                sent.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "test-noop")

        msg = MessageReceivedEvent(
            source="user",
            session_id="sess-no-assessment",
            patient_id="pat-cog-001",
            content="how are you",
            message_id="msg-noop",
        )
        await agent.handle_event(msg)
        await asyncio.sleep(0.05)

        assert len(sent) == 0

        await agent.stop()
        await bus.stop()

    async def test_llm_scoring_failure_defaults_to_zero(self, agent, bus, llm, state):
        """If the LLM returns a non-integer, the score should default to 0."""
        await bus.start()
        await agent.start()

        completed: list[AssessmentCompletedEvent] = []

        async def cap(event):
            if isinstance(event, AssessmentCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, cap, "test-fallback")

        # Queue bad responses for all GAD-7 items — should all default to 0
        for _ in range(7):
            llm.queue("not-a-number")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="gad7",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        for i in range(7):
            answer = MessageReceivedEvent(
                source="user",
                session_id="sess-cog-001",
                patient_id="pat-cog-001",
                content="some answer",
                message_id=f"msg-bad-{i}",
            )
            await agent.handle_event(answer)
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert completed[0].total_score == 0
        assert completed[0].severity == "minimal"

        await agent.stop()
        await bus.stop()

    async def test_score_clamped_to_max_per_item(self, agent, bus, llm, state):
        """LLM returning a score above max_per_item should be clamped."""
        await bus.start()
        await agent.start()

        completed: list[AssessmentCompletedEvent] = []

        async def cap(event):
            if isinstance(event, AssessmentCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, cap, "test-clamp")

        # PHQ-9 max per item is 3; queue 99 (should clamp to 3)
        for _ in range(9):
            llm.queue("99")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="phq9",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.05)

        for i in range(9):
            answer = MessageReceivedEvent(
                source="user",
                session_id="sess-cog-001",
                patient_id="pat-cog-001",
                content="always",
                message_id=f"msg-clamp-{i}",
            )
            await agent.handle_event(answer)
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        # 9 items × clamped 3 = 27
        assert completed[0].total_score == 27
        assert completed[0].severity == "severe"

        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Adaptive cognitive screening
# ---------------------------------------------------------------------------

class TestCognitiveScreening:

    def _make_task_response(self, domain: str = "memory") -> str:
        """Return a valid JSON task generation response."""
        return json.dumps({
            "domain": domain,
            "prompt": f"Please recall these 3 words: apple, table, penny. What were they?",
        })

    def _make_score_response(self, score: int = 2) -> str:
        """Return a valid JSON scoring response."""
        return json.dumps({
            "score": score,
            "rationale": "Patient responded appropriately.",
        })

    def _make_concerns_response(self, concerns: list[str] | None = None) -> str:
        """Return a valid JSON concerns list."""
        return json.dumps(concerns or [])

    async def test_cognitive_trigger_creates_screening_record(
        self, agent, bus, llm, state
    ):
        """ASSESSMENT_TRIGGERED(cognitive) should create a cognitive_screenings row."""
        # Queue enough responses for 8 tasks (2 gen + 2 score per domain × 4 domains = 16)
        # Plus 1 concerns call
        for domain in ["memory", "memory", "attention", "attention",
                       "orientation", "orientation", "executive_function", "executive_function"]:
            llm.queue(self._make_task_response(domain))
            llm.queue(self._make_score_response(2))
        llm.queue(self._make_concerns_response([]))

        await bus.start()
        await agent.start()

        started: list[CognitiveScreeningStartedEvent] = []

        async def cap(event):
            if isinstance(event, CognitiveScreeningStartedEvent):
                started.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_STARTED, cap, "test-cs-started")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="cognitive",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.3)  # Give time for all LLM calls

        assert len(started) == 1
        assert started[0].patient_id == "pat-cog-001"

        # Verify DB record was created
        screening_id = started[0].screening_id
        record = await state.get_cognitive_screening(screening_id)
        assert record is not None
        assert record["patient_id"] == "pat-cog-001"

        await agent.stop()
        await bus.stop()

    async def test_cognitive_screening_publishes_completed(
        self, agent, bus, llm, state
    ):
        """Cognitive screening should publish COGNITIVE_SCREENING_COMPLETED with a score."""
        for domain in ["memory", "memory", "attention", "attention",
                       "orientation", "orientation", "executive_function", "executive_function"]:
            llm.queue(self._make_task_response(domain))
            llm.queue(self._make_score_response(2))
        llm.queue(self._make_concerns_response([]))

        await bus.start()
        await agent.start()

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event):
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-cs-complete")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="cognitive",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.3)

        assert len(completed) == 1
        evt = completed[0]
        assert evt.patient_id == "pat-cog-001"
        assert evt.overall_score == 100.0  # All scored 2 (max) → 100%
        assert isinstance(evt.concerns, list)

        await agent.stop()
        await bus.stop()

    async def test_cognitive_screening_with_concerns(
        self, agent, bus, llm, state
    ):
        """Cognitive screening with poor domain scores should generate concerns.

        When all initial tasks score 0 (impaired), the adaptive pass adds up to
        2 extra probes per domain (4 domains × 2 = 8 extra), for a max of 15
        tasks total. We queue enough task+score pairs for the worst-case 15
        tasks (30 calls) plus the final concerns call.
        """
        domains_cycle = ["memory", "memory", "attention", "attention",
                         "orientation", "orientation", "executive_function", "executive_function",
                         # Adaptive extra probes (up to 2 per domain = 8 more, capped at 15)
                         "memory", "attention", "orientation", "executive_function",
                         "memory", "attention", "orientation"]
        for domain in domains_cycle:
            llm.queue(self._make_task_response(domain))
            llm.queue(self._make_score_response(0))
        # Concerns call — always last
        llm.queue(self._make_concerns_response(
            ["Significant memory impairment noted", "Attention deficits observed"]
        ))

        await bus.start()
        await agent.start()

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event):
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-cs-concerns")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="cognitive",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.5)  # Allow for adaptive extra probes

        assert len(completed) == 1
        evt = completed[0]
        assert evt.overall_score == 0.0
        assert len(evt.concerns) == 2

        # Verify DB record is complete
        record = await state.get_cognitive_screening(evt.screening_id)
        assert record is not None
        assert record["status"] == "completed"
        assert record["overall_score"] == 0.0
        assert len(record["concerns"]) == 2

        await agent.stop()
        await bus.stop()

    async def test_cognitive_screening_llm_failure_degrades_gracefully(
        self, agent, bus, state
    ):
        """LLM task generation failure should not crash the agent."""

        class FailingLLM(LLMProvider):
            async def complete(self, *args, **kwargs) -> LLMResponse:
                raise RuntimeError("LLM unavailable")

            async def stream(self, *args, **kwargs) -> AsyncIterator[str]:
                yield ""

        failing_agent = CognitiveAssessorAgent()
        failing_agent.initialize(bus, AdaConfig(), state, FailingLLM())

        await bus.start()
        await failing_agent.start()

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event):
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-cs-fail")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-cog-001",
            patient_id="pat-cog-001",
            instrument="cognitive",
        )
        await failing_agent.handle_event(trigger)
        await asyncio.sleep(0.3)

        # Should complete (possibly with 0 tasks) without raising
        assert len(completed) == 1
        evt = completed[0]
        assert evt.overall_score == 0.0

        await failing_agent.stop()
        await bus.stop()
