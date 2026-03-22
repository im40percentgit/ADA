"""
Integration test — WellnessCompanionAgent medication keyword → handoff → response.

Exercises the full handoff flow:
  1. WellnessCompanionAgent receives a MESSAGE_RECEIVED event containing medication
     keywords ("forgot my medication").
  2. It publishes AGENT_HANDOFF_REQUEST targeting "medication_manager".
  3. MockMedicationAgent (mixing in HandoffMixin) receives the request and
     publishes AGENT_HANDOFF_RESPONSE.
  4. WellnessCompanionAgent receives the response (subscribed to AGENT_HANDOFF_RESPONSE).

All state is in-memory SQLite. No LLM network calls are made.

@decision DEC-AGENT-003
@title Integration test wires WellnessCompanionAgent + MockMedicationAgent on shared bus
@status accepted
@rationale Proves the full keyword-detection → request_handoff → response
    pipeline works end-to-end with real event routing. Both agents are real
    implementations; MockLLMProvider substitutes only the external LLM API
    call, consistent with Sacred Practice #5.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from ada.agents.base import BaseAgent
from ada.agents.handoff import HandoffContext, HandoffMixin
from ada.agents.wellness_companion import WellnessCompanionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AdaEvent,
    AgentHandoffRequestEvent,
    AgentHandoffResponseEvent,
    EventTypes,
    MessageReceivedEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider — mirrors pattern from test_therapist.py
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """Deterministic LLM stub — returns canned response, records calls."""

    def __init__(self, canned: str = "I hear you.") -> None:
        self.canned = canned
        self.calls: list[dict] = []

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system})
        return LLMResponse(
            content=self.canned,
            model="mock",
            input_tokens=len(str(messages)),
            output_tokens=len(self.canned),
        )

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        yield self.canned


# ---------------------------------------------------------------------------
# MockMedicationAgent — receives handoffs
# ---------------------------------------------------------------------------

class MockMedicationAgent(BaseAgent, HandoffMixin):
    """Minimal medication agent stub that accepts handoffs."""

    def __init__(self) -> None:
        super().__init__()
        self.handled: list[HandoffContext] = []

    @property
    def name(self) -> str:
        return "medication_manager"

    @property
    def description(self) -> str:
        return "Mock medication manager for integration tests"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.AGENT_HANDOFF_REQUEST]

    async def handle_event(self, event: AdaEvent) -> None:
        if event.event_type == EventTypes.AGENT_HANDOFF_REQUEST:
            await self.handle_handoff_request(event)

    async def _process_handoff(self, context: HandoffContext) -> str:
        self.handled.append(context)
        return "Medication handoff accepted — tracking context noted"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    # Seed patient + session for FK constraints
    await sm.create_patient({
        "id": "pat-med", "name": "Med Patient", "dob": None,
        "preferences": {}, "emergency_contact": None, "caregiver_id": None,
    })
    await sm.create_session({"id": "sess-med", "patient_id": "pat-med"})
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
def therapist(bus, config, state, llm) -> WellnessCompanionAgent:
    agent = WellnessCompanionAgent()
    agent.initialize(bus, config, state, llm)
    return agent


@pytest.fixture
def med_agent(bus, config, state, llm) -> MockMedicationAgent:
    agent = MockMedicationAgent()
    agent.initialize(bus, config, state, llm)
    return agent


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestMedicationHandoffFlow:

    async def test_medication_keyword_triggers_handoff_request(
        self, therapist, med_agent, bus, state
    ):
        """'forgot my medication' in a message causes WellnessCompanionAgent to publish
        AGENT_HANDOFF_REQUEST targeting medication_manager."""
        await bus.start()
        await therapist.start()
        await med_agent.start()

        handoff_requests: list[AgentHandoffRequestEvent] = []

        async def capture_requests(event):
            if isinstance(event, AgentHandoffRequestEvent):
                handoff_requests.append(event)

        bus.subscribe(EventTypes.AGENT_HANDOFF_REQUEST, capture_requests, "test-req-cap")

        event = MessageReceivedEvent(
            session_id="sess-med",
            patient_id="pat-med",
            content="I forgot my medication this morning",
            message_id="msg-med-1",
        )
        await therapist.handle_event(event)
        await asyncio.sleep(0.15)

        assert len(handoff_requests) >= 1
        req = handoff_requests[0]
        assert req.target_agent == "medication_manager"
        assert req.from_agent == "wellness_companion"

        await therapist.stop()
        await med_agent.stop()
        await bus.stop()

    async def test_medication_agent_receives_handoff_and_responds(
        self, therapist, med_agent, bus, state
    ):
        """MockMedicationAgent receives the handoff request published by
        WellnessCompanionAgent and emits a response event."""
        await bus.start()
        await therapist.start()
        await med_agent.start()

        responses: list[AgentHandoffResponseEvent] = []

        async def capture_responses(event):
            if isinstance(event, AgentHandoffResponseEvent):
                responses.append(event)

        bus.subscribe(EventTypes.AGENT_HANDOFF_RESPONSE, capture_responses, "test-resp-cap")

        event = MessageReceivedEvent(
            session_id="sess-med",
            patient_id="pat-med",
            content="I forgot my medication this morning",
            message_id="msg-med-2",
        )
        await therapist.handle_event(event)
        await asyncio.sleep(0.2)

        assert len(responses) >= 1
        resp = responses[0]
        assert resp.from_agent == "medication_manager"
        assert resp.accepted is True

        await therapist.stop()
        await med_agent.stop()
        await bus.stop()

    async def test_medication_agent_records_handoff_context(
        self, therapist, med_agent, bus, state
    ):
        """HandoffContext received by medication agent contains the trigger content."""
        await bus.start()
        await therapist.start()
        await med_agent.start()

        msg_content = "I ran out of my prescription pills"
        event = MessageReceivedEvent(
            session_id="sess-med",
            patient_id="pat-med",
            content=msg_content,
            message_id="msg-med-3",
        )
        await therapist.handle_event(event)
        await asyncio.sleep(0.2)

        assert len(med_agent.handled) >= 1
        hc = med_agent.handled[0]
        assert hc.patient_id == "pat-med"
        assert hc.session_id == "sess-med"
        assert hc.from_agent == "wellness_companion"
        # Trigger content should be captured
        assert "trigger_content" in hc.context

        await therapist.stop()
        await med_agent.stop()
        await bus.stop()

    async def test_non_medication_message_does_not_trigger_handoff(
        self, therapist, med_agent, bus, state
    ):
        """A purely emotional message should NOT trigger a medication handoff."""
        await bus.start()
        await therapist.start()
        await med_agent.start()

        handoff_requests: list[AgentHandoffRequestEvent] = []

        async def capture_requests(event):
            if isinstance(event, AgentHandoffRequestEvent):
                handoff_requests.append(event)

        bus.subscribe(EventTypes.AGENT_HANDOFF_REQUEST, capture_requests, "test-nomatch")

        event = MessageReceivedEvent(
            session_id="sess-med",
            patient_id="pat-med",
            content="I feel really sad today",
            message_id="msg-med-4",
        )
        await therapist.handle_event(event)
        await asyncio.sleep(0.15)

        assert len(handoff_requests) == 0

        await therapist.stop()
        await med_agent.stop()
        await bus.stop()
