"""
Unit tests for KnowledgeAgent.

Coverage:
- Agent identity: name, description, supported_events
- Filtering: requests directed at a different agent are silently ignored
- Happy path: consultation with KB results → LLM synthesis → response published
- No results: FTS5 returns nothing → standard "no evidence" message
- LLM failure: LLM raises → fallback to raw evidence text
- request_id correlation: response.request_id matches request.request_id

Tests use real in-memory SQLite, real EventBus, real ClinicalKnowledgeBase,
and a MockLLMProvider stub (concrete LLMProvider subclass). No internal
module mocking per Sacred Practice #5.

@decision DEC-KNOWLEDGE-008
@title KnowledgeAgent tests use real in-memory SQLite and real FTS5 KB
@status accepted
@rationale Consistent with DEC-TEST-005: real SQLite exercises the actual
    FTS5 search path, catching tokenisation and query bugs that an in-memory
    mock would hide. The LLM is the only external boundary — a concrete stub
    returning canned text exercises the full synthesis/publish path. Real
    EventBus with asyncio.sleep(0.05) confirms event delivery without
    introducing test-only coupling to bus internals.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.knowledge_agent import KnowledgeAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AgentConsultationRequestEvent,
    AgentConsultationResponseEvent,
    EventTypes,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider (real LLMProvider subclass — no internal mocks)
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """
    Deterministic LLM stub with a per-test response queue.

    Callers push canned responses with queue_response(); each complete()
    call pops the next one. Raises any exception placed in raise_next.
    """

    def __init__(self, default_response: str = "Synthesized answer.") -> None:
        self.default_response = default_response
        self.response_queue: list[str] = []
        self.raise_next: Exception | None = None
        self.calls: list[dict] = []

    def queue_response(self, response: str) -> None:
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
        if self.raise_next is not None:
            exc = self.raise_next
            self.raise_next = None
            raise exc
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
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        for word in content.split():
            yield word + " "


# ---------------------------------------------------------------------------
# Seed data — three entries covering distinct clinical topics
# ---------------------------------------------------------------------------

_SEED_ENTRIES = [
    {
        "title": "Cognitive Restructuring",
        "category": "cbt_technique",
        "content": "Helps patients identify and challenge distorted thinking patterns.",
        "source": "Beck (2020)",
        "tags": "cbt anxiety depression",
    },
    {
        "title": "Deep Breathing",
        "category": "cbt_technique",
        "content": "Diaphragmatic breathing activates the parasympathetic nervous system.",
        "source": "Barlow (2018)",
        "tags": "anxiety breathing relaxation",
    },
    {
        "title": "Distress Tolerance",
        "category": "dbt_skill",
        "content": "TIPP skills for managing acute emotional distress.",
        "source": "Linehan (2014)",
        "tags": "dbt distress crisis",
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    """Initialised in-memory StateManager — isolated per test."""
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def kb(state):
    """Initialised ClinicalKnowledgeBase seeded with _SEED_ENTRIES."""
    from ada.knowledge.clinical_kb import ClinicalKnowledgeBase
    clinical_kb = ClinicalKnowledgeBase(state._conn)
    await clinical_kb.initialize()
    await clinical_kb.seed(_SEED_ENTRIES)
    return clinical_kb


@pytest_asyncio.fixture
async def bus():
    """Running EventBus — started and stopped around each test."""
    event_bus = EventBus()
    await event_bus.start()
    yield event_bus
    await event_bus.stop()


@pytest_asyncio.fixture
def config():
    return AdaConfig()


@pytest_asyncio.fixture
def llm():
    return MockLLMProvider()


@pytest_asyncio.fixture
async def knowledge_agent(bus, config, state, llm, kb):
    """Fully wired KnowledgeAgent with KB injected and started."""
    agent = KnowledgeAgent()
    agent.initialize(bus, config, state, llm)
    agent.set_kb(kb)
    await agent.start()
    yield agent
    await agent.stop()


# ---------------------------------------------------------------------------
# Helper: publish a consultation request and collect the response
# ---------------------------------------------------------------------------

def _make_request(
    *,
    target_agent: str = "knowledge_agent",
    question: str = "What CBT techniques help with anxiety?",
    request_id: str = "req-001",
    from_agent: str = "therapist",
    session_id: str = "session-001",
    patient_id: str = "patient-001",
) -> AgentConsultationRequestEvent:
    return AgentConsultationRequestEvent(
        source=from_agent,
        session_id=session_id,
        patient_id=patient_id,
        from_agent=from_agent,
        target_agent=target_agent,
        question=question,
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestKnowledgeAgentIdentity:
    def test_name(self):
        agent = KnowledgeAgent()
        assert agent.name == "knowledge_agent"

    def test_description(self):
        agent = KnowledgeAgent()
        assert agent.description
        assert isinstance(agent.description, str)
        assert len(agent.description) > 10

    def test_supported_events(self):
        agent = KnowledgeAgent()
        assert EventTypes.AGENT_CONSULTATION_REQUEST in agent.supported_events


class TestKnowledgeAgentIgnoresOtherTargets:
    @pytest.mark.asyncio
    async def test_ignores_consultation_for_other_agent(
        self, knowledge_agent, bus
    ):
        """A request targeting a different agent must not produce a response."""
        responses: list[AgentConsultationResponseEvent] = []

        async def collector(event):
            responses.append(event)

        bus.subscribe(EventTypes.AGENT_CONSULTATION_RESPONSE, collector, "test-collector")

        await bus.publish(_make_request(target_agent="other_agent"))
        await asyncio.sleep(0.05)

        assert responses == []


class TestKnowledgeAgentConsultation:
    @pytest.mark.asyncio
    async def test_consultation_returns_evidence(self, knowledge_agent, bus, llm):
        """Happy path: KB matches → LLM synthesizes → response published."""
        llm.queue_response("CBT cognitive restructuring is effective for anxiety (Beck 2020).")

        responses: list[AgentConsultationResponseEvent] = []
        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE,
            lambda e: responses.append(e),
            "test-happy",
        )

        await bus.publish(_make_request(question="cognitive restructuring anxiety"))
        await asyncio.sleep(0.1)

        assert len(responses) == 1
        resp = responses[0]
        assert isinstance(resp, AgentConsultationResponseEvent)
        # LLM synthesis answer should contain content from our canned response
        assert "Beck" in resp.answer or "cognitive" in resp.answer.lower()
        assert resp.from_agent == "knowledge_agent"

    @pytest.mark.asyncio
    async def test_consultation_no_results(self, knowledge_agent, bus, llm):
        """Query that matches no FTS5 entries → standard no-evidence message."""
        responses: list[AgentConsultationResponseEvent] = []
        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE,
            lambda e: responses.append(e),
            "test-no-results",
        )

        # A highly specific query unlikely to match the seed entries
        await bus.publish(
            _make_request(question="xyzzyx nonexistent xylophone quantum therapy")
        )
        await asyncio.sleep(0.1)

        assert len(responses) == 1
        assert responses[0].answer == "No relevant clinical evidence found."
        # LLM should NOT have been called
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_consultation_llm_failure_returns_raw_evidence(
        self, knowledge_agent, bus, llm
    ):
        """If the LLM raises, the agent falls back to raw evidence text."""
        llm.raise_next = RuntimeError("LLM unavailable")

        responses: list[AgentConsultationResponseEvent] = []
        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE,
            lambda e: responses.append(e),
            "test-llm-fail",
        )

        await bus.publish(_make_request(question="cognitive restructuring"))
        await asyncio.sleep(0.1)

        assert len(responses) == 1
        # Fallback should contain raw evidence fragments (title, source, content)
        answer = responses[0].answer
        assert answer  # non-empty
        # Raw evidence format: "1. [Title] (Source) — content"
        assert "[" in answer or "Cognitive" in answer

    @pytest.mark.asyncio
    async def test_response_includes_request_id(self, knowledge_agent, bus, llm):
        """response.request_id must match the request_id of the originating request."""
        llm.queue_response("Distress tolerance helps (Linehan 2014).")

        responses: list[AgentConsultationResponseEvent] = []
        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE,
            lambda e: responses.append(e),
            "test-req-id",
        )

        unique_id = "unique-request-id-abc123"
        await bus.publish(_make_request(question="distress tolerance", request_id=unique_id))
        await asyncio.sleep(0.1)

        assert len(responses) == 1
        assert responses[0].request_id == unique_id

    @pytest.mark.asyncio
    async def test_response_session_and_patient_ids_match(self, knowledge_agent, bus, llm):
        """Response event carries the same session_id and patient_id as the request."""
        llm.queue_response("Breathing techniques activate the parasympathetic system (Barlow 2018).")

        responses: list[AgentConsultationResponseEvent] = []
        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE,
            lambda e: responses.append(e),
            "test-ids",
        )

        await bus.publish(
            _make_request(
                question="deep breathing",
                session_id="sess-xyz",
                patient_id="pat-abc",
            )
        )
        await asyncio.sleep(0.1)

        assert len(responses) == 1
        resp = responses[0]
        assert resp.session_id == "sess-xyz"
        assert resp.patient_id == "pat-abc"
