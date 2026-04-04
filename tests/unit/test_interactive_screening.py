"""
Unit tests for CognitiveAssessorAgent interactive screening flow.

Tests the _run_interactive_screening() method which replaces the old self-play
approach with real patient interaction via EventBus events:
  - CognitiveTaskPresentedEvent published for each task
  - CognitiveTaskResponseEvent received from patient advances to next task
  - Adaptive probing: low scores trigger extra tasks
  - Timeout: no response within timeout scores task as 0
  - Visual task scoring integration (pattern_grid via task_scoring.py)

Uses real EventBus, real in-memory SQLite StateManager, and a MockLLMProvider
(genuine LLMProvider subclass). No mocks of internal modules (Sacred Practice #5).

@decision DEC-COG-007
@title Interactive screening tests use real EventBus with response injection
@status accepted
@rationale Tests inject CognitiveTaskResponseEvent into the EventBus to
    simulate patient responses. The agent's _wait_for_task_response() resolves
    naturally via its subscriber callback. This exercises the full event flow
    without mocking any internal module.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import pytest

from ada.agents.cognitive_assessor import CognitiveAssessorAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AdaEvent,
    AssessmentTriggeredEvent,
    CognitiveScreeningCompletedEvent,
    CognitiveScreeningStartedEvent,
    CognitiveTaskPresentedEvent,
    CognitiveTaskResponseEvent,
    EventTypes,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """Deterministic LLM stub with a per-call response queue."""

    def __init__(self, default_response: str = "{}") -> None:
        self.default_response = default_response
        self.response_queue: list[str] = []
        self.calls: list[dict] = []

    def queue(self, response: str) -> None:
        self.response_queue.append(response)

    def queue_many(self, responses: list[str]) -> None:
        self.response_queue.extend(responses)

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
# Helpers
# ---------------------------------------------------------------------------


def _make_text_task(domain: str, prompt: str = "What is today's date?") -> str:
    """Return a valid JSON LLM response for a text task generation."""
    return json.dumps({
        "domain": domain,
        "task_type": "text",
        "prompt": prompt,
        "task_data": {"expected_answer": "April 3, 2026"},
    })


def _make_pattern_grid_task(domain: str = "memory") -> str:
    """Return a valid JSON LLM response for a pattern_grid task generation."""
    return json.dumps({
        "domain": domain,
        "task_type": "pattern_grid",
        "prompt": "Remember the highlighted cells, then select them from memory.",
        "task_data": {"grid_size": 4, "highlighted_cells": [1, 5, 9, 13]},
    })


def _make_sequence_order_task(domain: str = "executive_function") -> str:
    """Return a valid JSON LLM response for a sequence_order task generation."""
    return json.dumps({
        "domain": domain,
        "task_type": "sequence_order",
        "prompt": "Put these months in order: March, January, February.",
        "task_data": {
            "items": ["March", "January", "February"],
            "correct_order": ["January", "February", "March"],
        },
    })


def _make_clock_reading_task(domain: str = "visuospatial") -> str:
    """Return a valid JSON LLM response for a clock_reading task generation."""
    return json.dumps({
        "domain": domain,
        "task_type": "clock_reading",
        "prompt": "What time does this clock show?",
        "task_data": {"hour": 3, "minute": 15, "correct_time": "3:15"},
    })


def _make_score_response(score: int = 2, rationale: str = "Good response") -> str:
    """Return a valid JSON LLM scoring response."""
    return json.dumps({"score": score, "rationale": rationale})


def _make_concerns_response(concerns: list[str] | None = None) -> str:
    """Return a valid JSON concerns list."""
    return json.dumps(concerns or [])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "pat-interactive-001",
        "name": "Interactive Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({
        "id": "sess-interactive-001",
        "patient_id": "pat-interactive-001",
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


def _make_trigger() -> AssessmentTriggeredEvent:
    """Standard trigger event for interactive cognitive screening."""
    return AssessmentTriggeredEvent(
        source="wellness_companion",
        session_id="sess-interactive-001",
        patient_id="pat-interactive-001",
        instrument="cognitive",
    )


# ---------------------------------------------------------------------------
# Helper: queue LLM responses for a full screening run
# ---------------------------------------------------------------------------


def _queue_full_screening_responses(
    llm: MockLLMProvider,
    *,
    score: int = 2,
    concerns: list[str] | None = None,
) -> None:
    """
    Queue enough LLM responses for a full 10-task interactive screening.

    Domain order: memory, attention, orientation, executive_function, visuospatial
    Each domain gets 2 tasks. The first task type alternates per domain mapping:
      - memory: pattern_grid, text
      - attention: text, text
      - orientation: text, text
      - executive_function: sequence_order, text
      - visuospatial: clock_reading, text

    For each task: 1 generation call. Text tasks also need 1 scoring call.
    Visual tasks (pattern_grid, sequence_order, clock_reading) are scored
    algorithmically so no LLM scoring call is needed.
    """
    # memory task 1: pattern_grid (no LLM score)
    llm.queue(_make_pattern_grid_task("memory"))
    # memory task 2: text (needs LLM score)
    llm.queue(_make_text_task("memory", "Recall the three words I told you earlier."))
    llm.queue(_make_score_response(score))
    # attention task 1: text
    llm.queue(_make_text_task("attention", "Count backwards from 100 by 7s."))
    llm.queue(_make_score_response(score))
    # attention task 2: text
    llm.queue(_make_text_task("attention", "Spell 'WORLD' backwards."))
    llm.queue(_make_score_response(score))
    # orientation task 1: text
    llm.queue(_make_text_task("orientation", "What is today's date?"))
    llm.queue(_make_score_response(score))
    # orientation task 2: text
    llm.queue(_make_text_task("orientation", "Where are you right now?"))
    llm.queue(_make_score_response(score))
    # executive_function task 1: sequence_order (no LLM score)
    llm.queue(_make_sequence_order_task("executive_function"))
    # executive_function task 2: text
    llm.queue(_make_text_task("executive_function", "Name as many animals as you can in 30 seconds."))
    llm.queue(_make_score_response(score))
    # visuospatial task 1: clock_reading (no LLM score)
    llm.queue(_make_clock_reading_task("visuospatial"))
    # visuospatial task 2: text
    llm.queue(_make_text_task("visuospatial", "Describe the layout of your living room."))
    llm.queue(_make_score_response(score))
    # concerns call — always last
    llm.queue(_make_concerns_response(concerns))


# ---------------------------------------------------------------------------
# Auto-responder: simulates patient responses via EventBus
# ---------------------------------------------------------------------------


class AutoResponder:
    """
    Subscribes to CognitiveTaskPresentedEvent and automatically publishes
    a CognitiveTaskResponseEvent with configurable response data.

    Used to drive the interactive screening flow in tests without manual
    event injection.
    """

    def __init__(
        self,
        bus: EventBus,
        *,
        text_response: str = "April 3, 2026",
        pattern_grid_response: list[int] | None = None,
        sequence_order_response: list[str] | None = None,
        clock_reading_response: str = "3:15",
        delay: float = 0.01,
    ) -> None:
        self.bus = bus
        self.text_response = text_response
        self.pattern_grid_response = pattern_grid_response or [1, 5, 9, 13]
        self.sequence_order_response = sequence_order_response or [
            "January", "February", "March"
        ]
        self.clock_reading_response = clock_reading_response
        self.delay = delay
        self.presented_events: list[CognitiveTaskPresentedEvent] = []

        bus.subscribe(
            EventTypes.COGNITIVE_TASK_PRESENTED,
            self._on_task_presented,
            "auto-responder",
        )

    async def _on_task_presented(self, event: AdaEvent) -> None:
        if not isinstance(event, CognitiveTaskPresentedEvent):
            return
        self.presented_events.append(event)

        # Small delay to ensure the agent's _wait_for_task_response subscriber
        # is registered before we publish the response
        await asyncio.sleep(self.delay)

        task_type = event.task_type
        if task_type == "pattern_grid":
            response: Any = self.pattern_grid_response
        elif task_type == "sequence_order":
            response = self.sequence_order_response
        elif task_type == "clock_reading":
            response = self.clock_reading_response
        else:
            response = self.text_response

        await self.bus.publish(
            CognitiveTaskResponseEvent(
                source="patient",
                screening_id=event.screening_id,
                task_index=event.task_index,
                response=response,
                session_id=event.session_id,
                patient_id=event.patient_id,
            )
        )

    def unsubscribe(self) -> None:
        self.bus.unsubscribe(EventTypes.COGNITIVE_TASK_PRESENTED, "auto-responder")


# ---------------------------------------------------------------------------
# Tests: Task presentation
# ---------------------------------------------------------------------------


class TestTaskPresentation:
    """Verify that interactive screening publishes CognitiveTaskPresentedEvent for each task."""

    async def test_publishes_task_presented_for_each_task(self, agent, bus, llm, state):
        """Interactive screening should publish 10 CognitiveTaskPresentedEvents (2 per domain)."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()
        responder = AutoResponder(bus)

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-completed")

        await agent.handle_event(_make_trigger())
        # Wait for the full screening flow
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        assert len(responder.presented_events) == 10

        # Verify domains are covered
        domains_seen = {e.domain for e in responder.presented_events}
        assert domains_seen == {
            "memory", "attention", "orientation",
            "executive_function", "visuospatial",
        }

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()

    async def test_task_presented_contains_correct_fields(self, agent, bus, llm, state):
        """Each CognitiveTaskPresentedEvent should have screening_id, task_index, domain, etc."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()
        responder = AutoResponder(bus)

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-fields")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(responder.presented_events) >= 1
        first = responder.presented_events[0]
        assert first.screening_id != ""
        assert first.task_index == 0
        assert first.domain == "memory"
        assert first.task_type == "pattern_grid"
        assert first.prompt != ""
        assert first.session_id == "sess-interactive-001"
        assert first.patient_id == "pat-interactive-001"

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()

    async def test_screening_publishes_started_event(self, agent, bus, llm, state):
        """Interactive screening should publish CognitiveScreeningStartedEvent."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()
        responder = AutoResponder(bus)

        started: list[CognitiveScreeningStartedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningStartedEvent):
                started.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_STARTED, cap, "test-started")

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap2(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap2, "test-started-complete")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(started) == 1
        assert started[0].patient_id == "pat-interactive-001"
        assert started[0].screening_id != ""

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Tests: Response advances screening
# ---------------------------------------------------------------------------


class TestResponseAdvancement:
    """Verify that receiving CognitiveTaskResponseEvent advances to the next task."""

    async def test_responses_advance_through_all_tasks(self, agent, bus, llm, state):
        """Each response should advance the screening to the next task until completion."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()
        responder = AutoResponder(bus)

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-advance")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        # Verify task indices are sequential
        indices = [e.task_index for e in responder.presented_events]
        assert indices == list(range(10))

        # Verify completion
        assert len(completed) == 1
        assert completed[0].overall_score == 100.0  # All perfect scores

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()

    async def test_screening_saves_to_db(self, agent, bus, llm, state):
        """Completed screening should persist results to the database."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()
        responder = AutoResponder(bus)

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-db")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        screening_id = completed[0].screening_id
        record = await state.get_cognitive_screening(screening_id)
        assert record is not None
        assert record["status"] == "completed"
        assert record["overall_score"] == 100.0
        assert len(record["tasks"]) == 10

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Tests: Adaptive probing
# ---------------------------------------------------------------------------


class TestAdaptiveProbing:
    """Verify that low scores trigger extra tasks for weak domains."""

    async def test_low_scores_trigger_extra_tasks(self, agent, bus, llm, state):
        """Domains with avg_score < 1.0 should get up to 2 extra tasks."""
        # Queue initial 10 tasks — all score 0 (impaired)
        # memory: pattern_grid (no LLM score), text (LLM score 0)
        llm.queue(_make_pattern_grid_task("memory"))
        llm.queue(_make_text_task("memory"))
        llm.queue(_make_score_response(0))
        # attention: text (0), text (0)
        llm.queue(_make_text_task("attention"))
        llm.queue(_make_score_response(0))
        llm.queue(_make_text_task("attention"))
        llm.queue(_make_score_response(0))
        # orientation: text (0), text (0)
        llm.queue(_make_text_task("orientation"))
        llm.queue(_make_score_response(0))
        llm.queue(_make_text_task("orientation"))
        llm.queue(_make_score_response(0))
        # executive_function: sequence_order (no LLM score), text (0)
        llm.queue(_make_sequence_order_task("executive_function"))
        llm.queue(_make_text_task("executive_function"))
        llm.queue(_make_score_response(0))
        # visuospatial: clock_reading (no LLM score), text (0)
        llm.queue(_make_clock_reading_task("visuospatial"))
        llm.queue(_make_text_task("visuospatial"))
        llm.queue(_make_score_response(0))

        # Adaptive probes: each of the 5 domains gets up to 2 extra tasks = 10 extra max
        # (capped at total 20 tasks). Queue enough for worst case.
        for _ in range(10):
            llm.queue(_make_text_task("probe"))
            llm.queue(_make_score_response(0))

        # Concerns
        llm.queue(_make_concerns_response(["Severe impairment across all domains"]))

        await bus.start()
        await agent.start()

        # Auto-responder that gives wrong answers for visual tasks
        responder = AutoResponder(
            bus,
            text_response="I don't know",
            pattern_grid_response=[],       # empty = score 0
            sequence_order_response=[],     # empty = score 0
            clock_reading_response="12:00", # wrong = score 0
        )

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-adaptive")

        await agent.handle_event(_make_trigger())
        for _ in range(200):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        # Should have more than 10 tasks due to adaptive probing
        total_presented = len(responder.presented_events)
        assert total_presented > 10, f"Expected >10 tasks with adaptive probing, got {total_presented}"
        # Max is 20
        assert total_presented <= 20

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()

    async def test_no_extra_tasks_when_scores_are_good(self, agent, bus, llm, state):
        """No adaptive probing when all domain averages >= 1.0."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()
        responder = AutoResponder(bus)

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-no-adaptive")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        # Exactly 10 tasks, no adaptive probing
        assert len(responder.presented_events) == 10

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Tests: Timeout handling
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Verify that missing responses within timeout score as 0."""

    async def test_timeout_scores_task_as_zero(self, agent, bus, llm, state):
        """If no CognitiveTaskResponseEvent arrives, the task should score 0."""
        # Queue a single text task generation — only 1 task, then we time out
        llm.queue(_make_text_task("memory", "What are 3 words?"))
        # We need generation for all 10 tasks plus scoring for text tasks,
        # but most will time out. Queue enough generation calls.
        for _ in range(9):
            llm.queue(_make_text_task("attention"))
        # Concerns
        llm.queue(_make_concerns_response([]))

        await bus.start()
        await agent.start()

        # Do NOT set up an auto-responder — all tasks will time out.
        # Override the timeout to be very short so tests don't hang.
        original_wait = agent._wait_for_task_response

        async def _fast_timeout(screening_id, task_index, timeout=300.0):
            return await original_wait(screening_id, task_index, timeout=0.05)

        agent._wait_for_task_response = _fast_timeout

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-timeout")

        await agent.handle_event(_make_trigger())
        for _ in range(200):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        # All tasks timed out → overall score 0
        assert completed[0].overall_score == 0.0

        await agent.stop()
        await bus.stop()

    async def test_partial_timeout_mix_produces_intermediate_score(self, agent, bus, llm, state):
        """Some tasks respond, others time out. Overall score should be between 0 and 100."""
        # Queue full screening responses (generation + text scoring)
        _queue_full_screening_responses(llm, score=2)
        # Also queue extra responses for potential adaptive probes
        for _ in range(10):
            llm.queue(_make_text_task("probe"))
            llm.queue(_make_score_response(0))
        llm.queue(_make_concerns_response([]))

        await bus.start()
        await agent.start()

        # Selective responder: responds to the first 5 tasks, times out the rest.
        # For visual tasks, gives correct answers when responding.
        presented: list[CognitiveTaskPresentedEvent] = []
        respond_count = 0

        async def _selective_responder(event: AdaEvent) -> None:
            nonlocal respond_count
            if not isinstance(event, CognitiveTaskPresentedEvent):
                return
            presented.append(event)
            if respond_count < 5:
                respond_count += 1
                await asyncio.sleep(0.01)
                # Choose response based on task type
                if event.task_type == "pattern_grid":
                    response: Any = event.task_data.get("highlighted_cells", [])
                elif event.task_type == "sequence_order":
                    response = event.task_data.get("correct_order", [])
                elif event.task_type == "clock_reading":
                    response = event.task_data.get("correct_time", "0:00")
                else:
                    response = "correct answer"
                await bus.publish(
                    CognitiveTaskResponseEvent(
                        source="patient",
                        screening_id=event.screening_id,
                        task_index=event.task_index,
                        response=response,
                        session_id=event.session_id,
                        patient_id=event.patient_id,
                    )
                )

        bus.subscribe(
            EventTypes.COGNITIVE_TASK_PRESENTED,
            _selective_responder,
            "selective-responder",
        )

        # Short timeout for non-responded tasks
        original_wait = agent._wait_for_task_response

        async def _fast_timeout(screening_id, task_index, timeout=300.0):
            return await original_wait(screening_id, task_index, timeout=0.1)

        agent._wait_for_task_response = _fast_timeout

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-partial")

        await agent.handle_event(_make_trigger())
        for _ in range(200):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        # Score should be between 0 and 100 (some tasks perfect, some timed out)
        score = completed[0].overall_score
        assert 0.0 < score < 100.0, f"Expected intermediate score, got {score}"

        bus.unsubscribe(EventTypes.COGNITIVE_TASK_PRESENTED, "selective-responder")
        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Tests: Visual task scoring integration
# ---------------------------------------------------------------------------


class TestVisualTaskScoring:
    """Verify that visual tasks are scored via task_scoring.py, not LLM."""

    async def test_pattern_grid_scored_algorithmically(self, agent, bus, llm, state):
        """pattern_grid responses should be scored by score_pattern_grid(), not LLM."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()

        # Responder gives perfect pattern_grid answers
        responder = AutoResponder(
            bus,
            pattern_grid_response=[1, 5, 9, 13],  # exact match
        )

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-pattern")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        # Find the pattern_grid task in the DB
        record = await state.get_cognitive_screening(completed[0].screening_id)
        tasks = record["tasks"]
        grid_tasks = [t for t in tasks if t.get("task_type") == "pattern_grid"]
        assert len(grid_tasks) >= 1
        # Perfect match → score 2
        assert grid_tasks[0]["score"] == 2
        assert "cells correct" in grid_tasks[0]["rationale"]

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()

    async def test_pattern_grid_partial_score(self, agent, bus, llm, state):
        """Partial pattern_grid matches should score 1 (borderline)."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()

        # Responder gives partial pattern_grid answers (3/4 correct = 75% → score 1)
        responder = AutoResponder(
            bus,
            pattern_grid_response=[1, 5, 9],  # 3 of 4 highlighted cells
        )

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-partial-grid")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        record = await state.get_cognitive_screening(completed[0].screening_id)
        tasks = record["tasks"]
        grid_tasks = [t for t in tasks if t.get("task_type") == "pattern_grid"]
        assert len(grid_tasks) >= 1
        # 3/4 = 75% → score 1 (borderline: 0.50 <= ratio <= 0.80)
        assert grid_tasks[0]["score"] == 1

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()

    async def test_sequence_order_scored_algorithmically(self, agent, bus, llm, state):
        """sequence_order responses should be scored by score_sequence_order()."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()

        # Perfect sequence order
        responder = AutoResponder(
            bus,
            sequence_order_response=["January", "February", "March"],
        )

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-sequence")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        record = await state.get_cognitive_screening(completed[0].screening_id)
        tasks = record["tasks"]
        seq_tasks = [t for t in tasks if t.get("task_type") == "sequence_order"]
        assert len(seq_tasks) >= 1
        assert seq_tasks[0]["score"] == 2
        assert "positions correct" in seq_tasks[0]["rationale"]

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()

    async def test_clock_reading_scored_algorithmically(self, agent, bus, llm, state):
        """clock_reading responses should be scored by score_clock_reading()."""
        _queue_full_screening_responses(llm, score=2)

        await bus.start()
        await agent.start()

        # Perfect clock reading
        responder = AutoResponder(
            bus,
            clock_reading_response="3:15",
        )

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-clock")

        await agent.handle_event(_make_trigger())
        for _ in range(100):
            if completed:
                break
            await asyncio.sleep(0.05)

        assert len(completed) == 1
        record = await state.get_cognitive_screening(completed[0].screening_id)
        tasks = record["tasks"]
        clock_tasks = [t for t in tasks if t.get("task_type") == "clock_reading"]
        assert len(clock_tasks) >= 1
        assert clock_tasks[0]["score"] == 2

        responder.unsubscribe()
        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Tests: Simulated screening backwards compat
# ---------------------------------------------------------------------------


class TestSimulatedScreeningBackwardsCompat:
    """Verify the old simulated screening is still accessible via cognitive_simulated."""

    async def test_simulated_screening_via_instrument_name(self, agent, bus, llm, state):
        """instrument='cognitive_simulated' should run the legacy simulated flow."""
        # Queue responses for 8-task simulated screening (4 domains x 2 tasks)
        for domain in ["memory", "memory", "attention", "attention",
                       "orientation", "orientation",
                       "executive_function", "executive_function"]:
            llm.queue(json.dumps({
                "domain": domain,
                "prompt": f"Simulated {domain} task",
            }))
            llm.queue(json.dumps({
                "score": 2,
                "rationale": "Simulated scoring",
            }))
        llm.queue(_make_concerns_response([]))

        await bus.start()
        await agent.start()

        completed: list[CognitiveScreeningCompletedEvent] = []

        async def cap(event: AdaEvent) -> None:
            if isinstance(event, CognitiveScreeningCompletedEvent):
                completed.append(event)

        bus.subscribe(EventTypes.COGNITIVE_SCREENING_COMPLETED, cap, "test-simulated")

        trigger = AssessmentTriggeredEvent(
            source="wellness_companion",
            session_id="sess-interactive-001",
            patient_id="pat-interactive-001",
            instrument="cognitive_simulated",
        )
        await agent.handle_event(trigger)
        await asyncio.sleep(0.5)

        assert len(completed) == 1
        assert completed[0].overall_score == 100.0

        await agent.stop()
        await bus.stop()
