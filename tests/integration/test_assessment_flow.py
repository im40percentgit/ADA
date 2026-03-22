"""
Integration test: assessment flow from WellnessCompanionAgent trigger to completion.

Verifies the full pipeline:
  1. User message containing assessment keyword → WellnessCompanionAgent publishes ASSESSMENT_TRIGGERED
  2. CognitiveAssessorAgent receives ASSESSMENT_TRIGGERED → publishes first question
  3. User answers all questions → CognitiveAssessorAgent scores and saves → publishes ASSESSMENT_COMPLETED
  4. PHQ-9 result persisted to assessment_results table

Also tests:
  - Cognitive screening triggered by "memory test" keyword
  - Both agents operate correctly when wired to the same EventBus

@decision DEC-TEST-005
@title Integration tests use real in-memory SQLite, real EventBus, MockLLMProvider
@status accepted
@rationale Sacred Practice #5: no internal mocks. All agents, StateManager,
    and EventBus run in real in-memory configuration. MockLLMProvider from
    conftest.py is a genuine LLMProvider subclass.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ada.agents.cognitive_assessor import CognitiveAssessorAgent
from ada.agents.wellness_companion import WellnessCompanionAgent
from ada.core.events import (
    AssessmentCompletedEvent,
    AssessmentTriggeredEvent,
    CognitiveScreeningCompletedEvent,
    CognitiveScreeningStartedEvent,
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
)


# ---------------------------------------------------------------------------
# Full PHQ-9 assessment flow
# ---------------------------------------------------------------------------

class TestAssessmentFlow:

    async def test_phq9_full_flow(self, state, bus, llm, config, patient_id, session_id):
        """
        Full PHQ-9 flow: ASSESSMENT_TRIGGERED → assessor drives questionnaire → completes.

        CognitiveAssessorAgent is wired directly. The trigger is published
        synthetically (as WellnessCompanionAgent would publish it) to isolate the
        assessor's behaviour from WellnessCompanionAgent's LLM calls.
        """
        assessor = CognitiveAssessorAgent()
        assessor.initialize(bus, config, state, llm)

        await bus.start()
        await assessor.start()

        completed: list[AssessmentCompletedEvent] = []
        questions: list[MessageSentEvent] = []

        async def on_completed(event):
            if isinstance(event, AssessmentCompletedEvent):
                completed.append(event)

        async def on_sent(event):
            if isinstance(event, MessageSentEvent) and event.agent_name == "cognitive_assessor":
                questions.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, on_completed, "int-complete")
        bus.subscribe(EventTypes.MESSAGE_SENT, on_sent, "int-questions")

        # CognitiveAssessorAgent needs a score for each of the 9 PHQ-9 items
        for _ in range(9):
            llm.queue_response("1")

        # Publish trigger directly (as WellnessCompanionAgent would)
        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id=session_id,
            patient_id=patient_id,
            instrument="phq9",
        )
        await bus.publish(trigger)
        await asyncio.sleep(0.1)

        # Verify first question was published by assessor
        assert len(questions) >= 1, "No questions published by cognitive assessor"
        assert "PHQ9 Question 1/9" in questions[0].content

        # Answer all 9 questions
        for i in range(9):
            answer = MessageReceivedEvent(
                source="user",
                session_id=session_id,
                patient_id=patient_id,
                content="several days",
                message_id=f"msg-int-answer-{i}",
            )
            await bus.publish(answer)
            await asyncio.sleep(0.1)

        # Verify assessment completed
        assert len(completed) == 1, f"Expected 1 ASSESSMENT_COMPLETED, got {len(completed)}"
        evt = completed[0]
        assert evt.instrument == "phq9"
        assert evt.patient_id == patient_id
        # Score should be 9 × 1 = 9 (mild)
        assert evt.total_score == 9
        assert evt.severity == "mild"

        # Verify persisted to DB
        results = await state.get_assessments(patient_id, instrument="phq9")
        assert len(results) == 1
        assert results[0]["total_score"] == 9

        await assessor.stop()
        await bus.stop()

    async def test_phq9_triggered_by_therapist_keyword(
        self, state, bus, llm, config, patient_id, session_id
    ):
        """
        When WellnessCompanionAgent and CognitiveAssessorAgent are both wired,
        a user message with 'phq9' triggers WellnessCompanionAgent to publish
        ASSESSMENT_TRIGGERED, which the assessor receives.

        This test verifies the inter-agent trigger path only — it doesn't
        drive the full questionnaire since WellnessCompanionAgent's 9 answer messages
        would each also generate LLM calls. We just verify the trigger fires.
        """
        therapist = WellnessCompanionAgent()
        therapist.initialize(bus, config, state, llm)

        assessor = CognitiveAssessorAgent()
        assessor.initialize(bus, config, state, llm)

        await bus.start()
        await therapist.start()
        await assessor.start()

        triggered: list[AssessmentTriggeredEvent] = []
        questions: list[MessageSentEvent] = []

        async def on_triggered(event):
            if isinstance(event, AssessmentTriggeredEvent):
                triggered.append(event)

        async def on_sent(event):
            if isinstance(event, MessageSentEvent) and event.agent_name == "cognitive_assessor":
                questions.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_TRIGGERED, on_triggered, "int-therapist-trigger")
        bus.subscribe(EventTypes.MESSAGE_SENT, on_sent, "int-therapist-q1")

        # WellnessCompanionAgent needs one LLM response; assessor needs one score for the first question
        llm.queue_response("I can help you with a PHQ-9 assessment.")
        llm.queue_response("1")  # score for first question answer (if any)

        msg = MessageReceivedEvent(
            source="user",
            session_id=session_id,
            patient_id=patient_id,
            content="Can we do the phq9 assessment?",
            message_id="msg-int-therapist-trigger",
        )
        await bus.publish(msg)
        await asyncio.sleep(0.15)

        # WellnessCompanionAgent should have triggered an assessment
        assert len(triggered) == 1
        assert triggered[0].instrument == "phq9"

        # Assessor should have published the first question
        assert len(questions) >= 1
        assert "PHQ9 Question 1/9" in questions[0].content

        await therapist.stop()
        await assessor.stop()
        await bus.stop()

    async def test_gad7_flow_completes_with_correct_severity(
        self, state, bus, llm, config, patient_id, session_id
    ):
        """GAD-7 triggered by 'gad7' keyword should complete with correct severity."""
        assessor = CognitiveAssessorAgent()
        assessor.initialize(bus, config, state, llm)

        await bus.start()
        await assessor.start()

        completed: list[AssessmentCompletedEvent] = []

        async def on_completed(event):
            if isinstance(event, AssessmentCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_COMPLETED, on_completed, "int-gad7-complete")

        # Score all items 2 → total 14 → moderate
        for _ in range(7):
            llm.queue_response("2")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id=session_id,
            patient_id=patient_id,
            instrument="gad7",
        )
        await bus.publish(trigger)
        await asyncio.sleep(0.1)

        for i in range(7):
            answer = MessageReceivedEvent(
                source="user",
                session_id=session_id,
                patient_id=patient_id,
                content="more than half the days",
                message_id=f"msg-gad-int-{i}",
            )
            await bus.publish(answer)
            await asyncio.sleep(0.1)

        assert len(completed) == 1
        assert completed[0].total_score == 14
        assert completed[0].severity == "moderate"

        await assessor.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Cognitive screening flow
# ---------------------------------------------------------------------------

class TestCognitiveScreeningFlow:

    async def test_cognitive_screening_full_flow(
        self, state, bus, llm, config, patient_id, session_id
    ):
        """
        Cognitive screening: ASSESSMENT_TRIGGERED(cognitive) →
        COGNITIVE_SCREENING_STARTED → tasks run → COGNITIVE_SCREENING_COMPLETED.
        """
        assessor = CognitiveAssessorAgent()
        assessor.initialize(bus, config, state, llm)

        await bus.start()
        await assessor.start()

        started: list[CognitiveScreeningStartedEvent] = []
        completed: list[CognitiveScreeningCompletedEvent] = []

        async def on_started(event):
            if isinstance(event, CognitiveScreeningStartedEvent):
                started.append(event)

        async def on_completed(event):
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_STARTED, on_started, "int-cs-started")
        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, on_completed, "int-cs-complete")

        # Queue: 2 task+score pairs per domain (8 total), then concerns
        for domain in ["memory", "memory", "attention", "attention",
                       "orientation", "orientation", "executive_function", "executive_function"]:
            llm.queue_response(json.dumps({
                "domain": domain,
                "prompt": f"Test {domain} task",
            }))
            llm.queue_response(json.dumps({
                "score": 2,
                "rationale": "Normal performance",
            }))
        llm.queue_response(json.dumps([]))  # No concerns

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id=session_id,
            patient_id=patient_id,
            instrument="cognitive",
        )
        await bus.publish(trigger)
        await asyncio.sleep(0.5)

        assert len(started) == 1, f"Expected COGNITIVE_SCREENING_STARTED, got {len(started)}"
        assert len(completed) == 1, f"Expected COGNITIVE_SCREENING_COMPLETED, got {len(completed)}"

        evt = completed[0]
        assert evt.patient_id == patient_id
        assert evt.overall_score == 100.0

        # Verify DB record
        record = await state.get_cognitive_screening(evt.screening_id)
        assert record is not None
        assert record["status"] == "completed"
        assert record["overall_score"] == 100.0
        assert isinstance(record["tasks"], list)
        assert len(record["tasks"]) == 8

        await assessor.stop()
        await bus.stop()

    async def test_therapist_triggers_cognitive_on_memory_test_phrase(
        self, state, bus, llm, config, patient_id, session_id
    ):
        """
        'memory test' in user message → WellnessCompanionAgent publishes ASSESSMENT_TRIGGERED(cognitive).
        """
        therapist = WellnessCompanionAgent()
        therapist.initialize(bus, config, state, llm)

        await bus.start()
        await therapist.start()

        triggered: list[AssessmentTriggeredEvent] = []

        async def on_triggered(event):
            if isinstance(event, AssessmentTriggeredEvent):
                triggered.append(event)

        bus.subscribe(EventTypes.ASSESSMENT_TRIGGERED, on_triggered, "int-trig-cognitive")

        # WellnessCompanionAgent LLM response
        llm.queue_response("Sure, let's do a memory test.")

        msg = MessageReceivedEvent(
            source="user",
            session_id=session_id,
            patient_id=patient_id,
            content="I'd like to do a memory test please",
            message_id="msg-memtest",
        )
        await bus.publish(msg)
        await asyncio.sleep(0.1)

        assert len(triggered) == 1
        assert triggered[0].instrument == "cognitive"

        await therapist.stop()
        await bus.stop()
