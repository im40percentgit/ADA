"""
Unit tests for ada.agents.handoff — HandoffContext and HandoffMixin.

Tests run against real EventBus and real StateManager (:memory:) with no
mocks. The MockTargetAgent is a genuine BaseAgent subclass that mixes in
HandoffMixin to exercise the receiving side of the protocol.

@decision DEC-AGENT-003
@title HandoffMixin tested via concrete agent subclass on real EventBus
@status accepted
@rationale Sacred Practice #5: no mocks for internal modules. HandoffContext
    is a pure dataclass — verified by construction. HandoffMixin is tested
    by mixing it into a concrete BaseAgent subclass and publishing real events
    through a live EventBus. This mirrors exactly what production agents do.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from ada.agents.base import BaseAgent
from ada.agents.handoff import HandoffContext, HandoffMixin
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AgentHandoffRequestEvent,
    AgentHandoffResponseEvent,
    EventTypes,
    AdaEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# Minimal LLM stub
# ---------------------------------------------------------------------------

class StubLLM(LLMProvider):
    async def complete(self, messages, *, max_tokens=1024, temperature=0.7,
                       system=None) -> LLMResponse:
        return LLMResponse(content="ok", model="stub", input_tokens=1, output_tokens=1)

    async def stream(self, messages, *, max_tokens=1024, temperature=0.7,
                     system=None) -> AsyncIterator[str]:
        yield "ok"


# ---------------------------------------------------------------------------
# Concrete agent that uses HandoffMixin (receiving side)
# ---------------------------------------------------------------------------

class MockTargetAgent(BaseAgent, HandoffMixin):
    """Minimal agent that receives handoffs via HandoffMixin."""

    def __init__(self) -> None:
        super().__init__()
        self.received_contexts: list[HandoffContext] = []

    @property
    def name(self) -> str:
        return "mock_target"

    @property
    def description(self) -> str:
        return "Mock target agent for handoff tests"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.AGENT_HANDOFF_REQUEST]

    async def handle_event(self, event: AdaEvent) -> None:
        if event.event_type == EventTypes.AGENT_HANDOFF_REQUEST:
            await self.handle_handoff_request(event)

    async def _process_handoff(self, context: HandoffContext) -> str:
        self.received_contexts.append(context)
        return f"processed by {self.name}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def state() -> StateManager:
    sm = StateManager(":memory:")
    await sm.initialize()
    yield sm
    await sm.close()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def config() -> AdaConfig:
    return AdaConfig()


@pytest.fixture
def llm() -> StubLLM:
    return StubLLM()


@pytest.fixture
def target_agent(bus, config, state, llm) -> MockTargetAgent:
    agent = MockTargetAgent()
    agent.initialize(bus, config, state, llm)
    return agent


# ---------------------------------------------------------------------------
# HandoffContext
# ---------------------------------------------------------------------------

class TestHandoffContext:

    def test_construction_with_required_fields(self):
        hc = HandoffContext(
            session_id="sess-1",
            patient_id="pat-1",
            from_agent="therapist",
            reason="test reason",
        )
        assert hc.session_id == "sess-1"
        assert hc.patient_id == "pat-1"
        assert hc.from_agent == "therapist"
        assert hc.reason == "test reason"
        assert hc.context == {}
        assert hc.request_id == ""

    def test_construction_with_all_fields(self):
        hc = HandoffContext(
            session_id="sess-2",
            patient_id="pat-2",
            from_agent="therapist",
            reason="medication query",
            context={"trigger": "forgot my medication"},
            request_id="uuid-abc",
        )
        assert hc.context == {"trigger": "forgot my medication"}
        assert hc.request_id == "uuid-abc"

    def test_context_defaults_to_empty_dict(self):
        hc = HandoffContext(
            session_id="s", patient_id="p", from_agent="a", reason="r"
        )
        # Mutable default — each instance gets its own dict
        assert hc.context is not HandoffContext(
            session_id="s", patient_id="p", from_agent="a", reason="r"
        ).context


# ---------------------------------------------------------------------------
# HandoffMixin — receiving side
# ---------------------------------------------------------------------------

class TestHandoffMixin:

    async def test_non_handoff_event_is_ignored(self, target_agent, bus, config, state, llm):
        await bus.start()
        await target_agent.start()

        # Publish a non-handoff event
        from ada.core.events import SessionStartedEvent
        await bus.publish(SessionStartedEvent(session_id="s", patient_id="p"))
        await asyncio.sleep(0.05)

        assert target_agent.received_contexts == []
        await target_agent.stop()
        await bus.stop()

    async def test_handoff_to_different_target_is_ignored(self, target_agent, bus, config, state, llm):
        await bus.start()
        await target_agent.start()

        event = AgentHandoffRequestEvent(
            source="therapist",
            session_id="sess-1",
            patient_id="pat-1",
            from_agent="therapist",
            target_agent="someone_else",   # not "mock_target"
            handoff_reason="irrelevant",
            context={},
            request_id="req-1",
        )
        await target_agent.handle_event(event)
        await asyncio.sleep(0.05)

        assert target_agent.received_contexts == []
        await target_agent.stop()
        await bus.stop()

    async def test_handoff_to_this_agent_is_processed(self, target_agent, bus, config, state, llm):
        await bus.start()
        await target_agent.start()

        event = AgentHandoffRequestEvent(
            source="therapist",
            session_id="sess-1",
            patient_id="pat-1",
            from_agent="therapist",
            target_agent="mock_target",
            handoff_reason="medication question",
            context={"trigger": "my pills"},
            request_id="req-42",
        )
        await target_agent.handle_event(event)
        await asyncio.sleep(0.1)

        assert len(target_agent.received_contexts) == 1
        hc = target_agent.received_contexts[0]
        assert hc.from_agent == "therapist"
        assert hc.reason == "medication question"
        assert hc.context == {"trigger": "my pills"}
        assert hc.request_id == "req-42"

        await target_agent.stop()
        await bus.stop()

    async def test_handoff_publishes_response_event(self, target_agent, bus, config, state, llm):
        await bus.start()
        await target_agent.start()

        responses: list[AgentHandoffResponseEvent] = []

        async def capture(event):
            if isinstance(event, AgentHandoffResponseEvent):
                responses.append(event)

        bus.subscribe(EventTypes.AGENT_HANDOFF_RESPONSE, capture, "test-capture")

        event = AgentHandoffRequestEvent(
            source="therapist",
            session_id="sess-1",
            patient_id="pat-1",
            from_agent="therapist",
            target_agent="mock_target",
            handoff_reason="test",
            context={},
            request_id="req-99",
        )
        await target_agent.handle_event(event)
        await asyncio.sleep(0.1)

        assert len(responses) == 1
        resp = responses[0]
        assert resp.request_id == "req-99"
        assert resp.accepted is True
        assert resp.from_agent == "mock_target"
        assert "mock_target" in resp.notes

        await target_agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Round-trip: request → response via EventBus
# ---------------------------------------------------------------------------

class TestHandoffRoundTrip:

    async def test_request_response_round_trip(self, target_agent, bus, config, state, llm):
        """Publish a handoff request via bus; target agent responds via bus."""
        await bus.start()
        await target_agent.start()

        responses: list[AgentHandoffResponseEvent] = []

        async def capture(event):
            if isinstance(event, AgentHandoffResponseEvent):
                responses.append(event)

        bus.subscribe(EventTypes.AGENT_HANDOFF_RESPONSE, capture, "round-trip-capture")

        # Publish through bus (not direct call)
        request_event = AgentHandoffRequestEvent(
            source="therapist",
            session_id="sess-rt",
            patient_id="pat-rt",
            from_agent="therapist",
            target_agent="mock_target",
            handoff_reason="round trip test",
            context={"data": "value"},
            request_id="rt-001",
        )
        await bus.publish(request_event)

        # Give bus time to dispatch
        await asyncio.sleep(0.15)

        assert len(responses) == 1
        assert responses[0].request_id == "rt-001"
        assert responses[0].accepted is True

        await target_agent.stop()
        await bus.stop()
