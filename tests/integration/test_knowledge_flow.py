"""
Integration tests for the TherapistAgent ↔ KnowledgeAgent consultation flow.

Verifies end-to-end: clinical keyword in user message → TherapistAgent fires
AGENT_CONSULTATION_REQUEST → KnowledgeAgent responds → TherapistAgent enriches
system prompt with evidence before generating its LLM response.

Uses a real EventBus, in-memory SQLite StateManager, MockLLMProvider from
conftest.py, and a seeded ClinicalKnowledgeBase — no external mocks.

@decision DEC-TEST-007
@title Consultation flow tests use real agents and seeded KB
@status accepted
@rationale Integration tests must exercise the complete consultation chain:
    EventBus routing, KnowledgeAgent FTS5 search, LLM synthesis, and
    TherapistAgent system-prompt enrichment. A seeded in-memory KB provides
    deterministic search results without touching production data.
"""

from __future__ import annotations

import asyncio

import pytest

from ada.agents.knowledge_agent import KnowledgeAgent
from ada.agents.therapist import TherapistAgent
from ada.core.events import (
    AgentConsultationRequestEvent,
    AgentConsultationResponseEvent,
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
)
from ada.knowledge.clinical_kb import ClinicalKnowledgeBase

from .conftest import MockLLMProvider

# ---------------------------------------------------------------------------
# KB seed data — three representative entries covering cbt, breathing, dbt
# ---------------------------------------------------------------------------

_SEED_ENTRIES = [
    {
        "title": "Cognitive Restructuring",
        "category": "cbt_technique",
        "content": (
            "Helps patients identify and challenge distorted thinking patterns."
        ),
        "source": "Beck (2020)",
        "tags": "cbt anxiety depression cognitive-distortions",
    },
    {
        "title": "Deep Breathing",
        "category": "cbt_technique",
        "content": (
            "Diaphragmatic breathing activates the parasympathetic nervous "
            "system to reduce anxiety."
        ),
        "source": "Barlow (2018)",
        "tags": "anxiety breathing relaxation grounding",
    },
    {
        "title": "Distress Tolerance",
        "category": "dbt_skill",
        "content": (
            "TIPP skills: Temperature, Intense exercise, Paced breathing, "
            "Progressive relaxation."
        ),
        "source": "Linehan (2014)",
        "tags": "dbt distress crisis tolerance",
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def kb(state):
    """Seeded ClinicalKnowledgeBase sharing the StateManager's connection."""
    clinical_kb = ClinicalKnowledgeBase(state._conn)
    await clinical_kb.initialize()
    await clinical_kb.seed(_SEED_ENTRIES)
    return clinical_kb


@pytest.fixture
async def knowledge_agent(bus, config, state, llm, kb):
    """Fully wired, started KnowledgeAgent with seeded KB."""
    agent = KnowledgeAgent()
    agent.initialize(bus, config, state, llm)
    agent.set_kb(kb)
    await bus.start()
    await agent.start()
    yield agent
    await agent.stop()
    await bus.stop()


@pytest.fixture
async def therapist_only(bus, config, state, llm, patient_id, session_id):
    """TherapistAgent wired to a running bus — no KnowledgeAgent registered."""
    # Bus may already be running from another fixture; start idempotently
    if not bus.is_running:
        await bus.start()
    agent = TherapistAgent()
    agent.initialize(bus, config, state, llm)
    await agent.start()
    yield agent
    await agent.stop()
    if bus.is_running:
        await bus.stop()


@pytest.fixture
async def both_agents(bus, config, state, llm, kb, patient_id, session_id):
    """Both TherapistAgent and KnowledgeAgent running on the same bus."""
    therapist = TherapistAgent()
    therapist.initialize(bus, config, state, llm)

    knowledge = KnowledgeAgent()
    knowledge.initialize(bus, config, state, llm)
    knowledge.set_kb(kb)

    await bus.start()
    await therapist.start()
    await knowledge.start()
    yield therapist, knowledge
    await therapist.stop()
    await knowledge.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# test_consultation_round_trip
# ---------------------------------------------------------------------------

class TestConsultationRoundTrip:
    """KnowledgeAgent receives a request and publishes a response."""

    async def test_consultation_round_trip(self, knowledge_agent, bus):
        """
        Publishing an AGENT_CONSULTATION_REQUEST targeting knowledge_agent
        should produce an AGENT_CONSULTATION_RESPONSE with a non-empty answer.
        """
        responses: list[AgentConsultationResponseEvent] = []

        async def capture(event):
            responses.append(event)

        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE, capture, "round-trip-capture"
        )

        await bus.publish(
            AgentConsultationRequestEvent(
                source="test",
                session_id="sess-rt-001",
                patient_id="pat-rt-001",
                from_agent="test",
                target_agent="knowledge_agent",
                question="What breathing techniques help with anxiety?",
                request_id="req-rt-001",
            )
        )

        # Allow KnowledgeAgent to process and respond
        await asyncio.sleep(0.5)

        assert len(responses) == 1
        assert responses[0].request_id == "req-rt-001"
        assert len(responses[0].answer) > 0

    async def test_consultation_ignored_for_wrong_target(self, knowledge_agent, bus):
        """KnowledgeAgent should not respond to requests directed elsewhere."""
        responses: list[AgentConsultationResponseEvent] = []

        async def capture(event):
            responses.append(event)

        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE, capture, "wrong-target-capture"
        )

        await bus.publish(
            AgentConsultationRequestEvent(
                source="test",
                session_id="sess-wt-001",
                patient_id="pat-wt-001",
                from_agent="test",
                target_agent="some_other_agent",
                question="Any question",
                request_id="req-wt-001",
            )
        )

        await asyncio.sleep(0.3)
        assert len(responses) == 0


# ---------------------------------------------------------------------------
# test_therapist_keyword_triggers_consultation
# ---------------------------------------------------------------------------

class TestTherapistKeywordTrigger:
    """Messages with clinical keywords cause TherapistAgent to publish a request."""

    async def test_keyword_triggers_consultation_request(
        self, therapist_only, bus, session_id, patient_id
    ):
        """
        A message containing a consultation keyword ('breathing technique')
        should cause TherapistAgent to publish an AGENT_CONSULTATION_REQUEST
        targeting knowledge_agent.
        """
        requests: list[AgentConsultationRequestEvent] = []

        async def capture(event):
            if isinstance(event, AgentConsultationRequestEvent):
                requests.append(event)

        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_REQUEST, capture, "request-capture"
        )

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="Can you teach me a breathing technique for anxiety?",
                message_id="msg-kw-001",
            )
        )

        await asyncio.sleep(0.5)

        assert len(requests) >= 1
        assert requests[0].target_agent == "knowledge_agent"
        assert requests[0].from_agent == "therapist"

    async def test_cbt_keyword_triggers_consultation(
        self, therapist_only, bus, session_id, patient_id
    ):
        """'cbt' keyword should trigger a consultation request."""
        requests: list[AgentConsultationRequestEvent] = []

        async def capture(event):
            if isinstance(event, AgentConsultationRequestEvent):
                requests.append(event)

        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_REQUEST, capture, "cbt-capture"
        )

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="I've heard CBT can help — what does it involve?",
                message_id="msg-cbt-001",
            )
        )

        await asyncio.sleep(0.5)
        assert len(requests) >= 1

    async def test_phrase_trigger_how_do_i(
        self, therapist_only, bus, session_id, patient_id
    ):
        """'how do i' phrase should trigger a consultation request."""
        requests: list[AgentConsultationRequestEvent] = []

        async def capture(event):
            if isinstance(event, AgentConsultationRequestEvent):
                requests.append(event)

        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_REQUEST, capture, "phrase-capture"
        )

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="How do I manage my anxiety when it gets overwhelming?",
                message_id="msg-phrase-001",
            )
        )

        await asyncio.sleep(0.5)
        assert len(requests) >= 1


# ---------------------------------------------------------------------------
# test_therapist_no_keyword_no_consultation
# ---------------------------------------------------------------------------

class TestNoKeywordNoConsultation:
    """Messages without clinical keywords must not trigger consultation."""

    async def test_sad_message_no_consultation(
        self, therapist_only, bus, session_id, patient_id
    ):
        """
        'I feel sad today' contains no consultation keywords — no
        AGENT_CONSULTATION_REQUEST should be published.
        """
        requests: list[AgentConsultationRequestEvent] = []

        async def capture(event):
            if isinstance(event, AgentConsultationRequestEvent):
                requests.append(event)

        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_REQUEST, capture, "no-consult-capture"
        )

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="I feel sad today.",
                message_id="msg-sad-001",
            )
        )

        await asyncio.sleep(0.4)
        assert len(requests) == 0

    async def test_greeting_no_consultation(
        self, therapist_only, bus, session_id, patient_id
    ):
        """A simple greeting triggers no consultation."""
        requests: list[AgentConsultationRequestEvent] = []

        async def capture(event):
            if isinstance(event, AgentConsultationRequestEvent):
                requests.append(event)

        bus.subscribe(
            EventTypes.AGENT_CONSULTATION_REQUEST, capture, "greeting-capture"
        )

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="Hello, I just wanted to check in today.",
                message_id="msg-greet-001",
            )
        )

        await asyncio.sleep(0.4)
        assert len(requests) == 0


# ---------------------------------------------------------------------------
# test_therapist_proceeds_without_evidence_on_timeout
# ---------------------------------------------------------------------------

class TestTimeoutGraceful:
    """TherapistAgent must not hang when KnowledgeAgent is absent."""

    async def test_no_knowledge_agent_still_responds(
        self, bus, config, state, llm, patient_id, session_id
    ):
        """
        If no KnowledgeAgent is registered, TherapistAgent should time out
        cleanly (~2s) and still publish a MessageSentEvent.
        """
        if not bus.is_running:
            await bus.start()

        therapist = TherapistAgent()
        therapist.initialize(bus, config, state, llm)
        await therapist.start()

        sent_events: list[MessageSentEvent] = []

        async def capture(event):
            sent_events.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "timeout-capture")

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="Can you suggest a coping strategy for panic attacks?",
                message_id="msg-timeout-001",
            )
        )

        # Must resolve within 3.5s (2s timeout + processing margin)
        await asyncio.sleep(3.5)

        await therapist.stop()
        await bus.stop()

        assert len(sent_events) == 1, (
            "TherapistAgent should respond even without KnowledgeAgent"
        )

    async def test_timeout_uses_base_system_prompt(
        self, bus, config, state, llm, patient_id, session_id
    ):
        """
        When consultation times out, the LLM call must use the plain
        _SYSTEM_PROMPT with no evidence appendage.
        """
        if not bus.is_running:
            await bus.start()

        therapist = TherapistAgent()
        therapist.initialize(bus, config, state, llm)
        await therapist.start()

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="What mindfulness exercises do you recommend?",
                message_id="msg-timeout-sys-001",
            )
        )

        await asyncio.sleep(3.5)

        await therapist.stop()
        await bus.stop()

        assert len(llm.calls) == 1
        system_used = llm.calls[0]["system"]
        assert "Relevant clinical evidence" not in system_used


# ---------------------------------------------------------------------------
# test_full_pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """End-to-end: keyword → consultation → enriched system prompt → response."""

    async def test_full_pipeline_enriches_system_prompt(
        self, bus, config, state, kb, patient_id, session_id
    ):
        """
        A message with a clinical keyword should cause:
          1. TherapistAgent to fire a consultation request.
          2. KnowledgeAgent to search the KB and respond with evidence.
          3. TherapistAgent to call the LLM with an enriched system prompt
             containing "Relevant clinical evidence".
          4. A MessageSentEvent to be published with the LLM response.

        Uses separate LLM providers per agent to avoid shared-queue ordering
        ambiguity. The KB uses 'breathing anxiety' — a query that reliably
        returns FTS5 results from the seed data.
        """
        kb_llm = MockLLMProvider(
            canned_response="Diaphragmatic breathing activates the parasympathetic system (Barlow 2018)."
        )
        therapist_llm = MockLLMProvider(
            canned_response="Here is how you can use breathing to manage anxiety."
        )

        therapist = TherapistAgent()
        therapist.initialize(bus, config, state, therapist_llm)

        knowledge = KnowledgeAgent()
        knowledge.initialize(bus, config, state, kb_llm)
        knowledge.set_kb(kb)

        await bus.start()
        await therapist.start()
        await knowledge.start()

        sent_events: list[MessageSentEvent] = []

        async def capture(event):
            sent_events.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "pipeline-capture")

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                # 'breathing anxiety' produces FTS5 hits from seed data
                content="breathing anxiety",
                message_id="msg-pipeline-001",
            )
        )

        # Allow full round-trip: consultation + therapist LLM call
        await asyncio.sleep(1.5)

        await therapist.stop()
        await knowledge.stop()
        await bus.stop()

        assert len(sent_events) == 1
        assert sent_events[0].agent_name == "therapist"

        # The therapist's LLM call must have received enriched system prompt
        assert len(therapist_llm.calls) == 1
        system_used = therapist_llm.calls[0]["system"]
        assert "Relevant clinical evidence" in system_used, (
            f"Expected enriched system prompt, got: {system_used[:200]}"
        )

    async def test_full_pipeline_message_sent_content(
        self, bus, config, state, kb, patient_id, session_id
    ):
        """
        The MessageSentEvent content should match the therapist's LLM response.

        Uses separate MockLLMProvider instances for KnowledgeAgent and
        TherapistAgent so the LLM call ordering is unambiguous — no shared
        queue to race on.
        """
        kb_llm = MockLLMProvider(canned_response="KB synthesis: breathing reduces cortisol.")
        therapist_llm = MockLLMProvider(canned_response="Let me walk you through a breathing exercise.")

        therapist = TherapistAgent()
        therapist.initialize(bus, config, state, therapist_llm)

        knowledge = KnowledgeAgent()
        knowledge.initialize(bus, config, state, kb_llm)
        knowledge.set_kb(kb)

        await bus.start()
        await therapist.start()
        await knowledge.start()

        sent_events: list[MessageSentEvent] = []

        async def capture(event):
            sent_events.append(event)

        bus.subscribe(EventTypes.MESSAGE_SENT, capture, "content-check-capture")

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="I want to practice mindfulness breathing",
                message_id="msg-content-001",
            )
        )

        await asyncio.sleep(1.5)

        await therapist.stop()
        await knowledge.stop()
        await bus.stop()

        assert len(sent_events) == 1
        assert sent_events[0].content == therapist_llm.canned_response

    async def test_no_keyword_no_evidence_in_prompt(
        self, both_agents, bus, llm, session_id, patient_id
    ):
        """
        A message without clinical keywords should NOT include evidence
        in the system prompt, even when KnowledgeAgent is available.
        """
        _, _ = both_agents

        await bus.publish(
            MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content="I feel a bit down today.",
                message_id="msg-no-kw-001",
            )
        )

        await asyncio.sleep(0.5)

        assert len(llm.calls) == 1
        system_used = llm.calls[0]["system"]
        assert "Relevant clinical evidence" not in system_used
