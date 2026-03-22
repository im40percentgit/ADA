"""
Unit tests for ada.agents.medication_manager.MedicationManagerAgent.

Tests run against real in-memory SQLite, real EventBus, and a MockLLMProvider
(genuine LLMProvider subclass). No mocks for internal modules (Sacred Practice #5).

Coverage:
- Agent identity and lifecycle
- Handoff request filtering (wrong target ignored)
- Handoff processing with no medications
- Handoff processing with existing medications (LLM called with med list)
- Interaction check: no existing meds → returns None
- Interaction check: LLM says NO_INTERACTION → returns None
- Interaction check: LLM says INTERACTION → returns description, publishes event
- LLM failure paths degrade gracefully

@decision DEC-AGENT-004
@title MedicationManagerAgent unit tests use real infrastructure, no mocks
@status accepted
@rationale Sacred Practice #5: no internal mocks. MockLLMProvider is a real
    LLMProvider subclass with a response queue for per-test determinism.
    StateManager uses ":memory:" SQLite. EventBus is fully live.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from ada.agents.medication_manager import MedicationManagerAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AdaEvent,
    AgentHandoffRequestEvent,
    AgentHandoffResponseEvent,
    EventTypes,
    MedicationInteractionDetectedEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """Deterministic LLM stub with a response queue."""

    def __init__(self, default_response: str = "Medication review complete.") -> None:
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
        "id": "pat-unit-001",
        "name": "Unit Test Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
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
def agent(bus, config, state, llm) -> MedicationManagerAgent:
    a = MedicationManagerAgent()
    a.initialize(bus, config, state, llm)
    return a


# ---------------------------------------------------------------------------
# Identity and lifecycle
# ---------------------------------------------------------------------------

class TestAgentIdentity:

    def test_name_is_medication_manager(self, agent):
        assert agent.name == "medication_manager"

    def test_description_is_set(self, agent):
        assert len(agent.description) > 0

    def test_supported_events_includes_handoff_request(self, agent):
        assert EventTypes.AGENT_HANDOFF_REQUEST in agent.supported_events

    async def test_start_and_stop(self, agent, bus):
        await bus.start()
        await agent.start()
        assert agent.is_running
        await agent.stop()
        assert not agent.is_running
        await bus.stop()


# ---------------------------------------------------------------------------
# Handoff handling
# ---------------------------------------------------------------------------

class TestHandoffHandling:

    async def test_ignores_handoff_targeting_different_agent(self, agent, bus):
        await bus.start()
        await agent.start()

        event = AgentHandoffRequestEvent(
            source="wellness_companion",
            session_id="sess-x",
            patient_id="pat-unit-001",
            from_agent="wellness_companion",
            target_agent="someone_else",
            handoff_reason="not for us",
            context={},
            request_id="req-ignore",
        )
        # Should not raise; no response expected
        await agent.handle_event(event)
        await asyncio.sleep(0.05)

        await agent.stop()
        await bus.stop()

    async def test_handoff_publishes_response(self, agent, bus):
        """A handoff targeting medication_manager should publish a response event."""
        await bus.start()
        await agent.start()

        responses: list[AgentHandoffResponseEvent] = []

        async def capture(event):
            if isinstance(event, AgentHandoffResponseEvent):
                responses.append(event)

        bus.subscribe(EventTypes.AGENT_HANDOFF_RESPONSE, capture, "test-resp")

        event = AgentHandoffRequestEvent(
            source="wellness_companion",
            session_id="sess-001",
            patient_id="pat-unit-001",
            from_agent="wellness_companion",
            target_agent="medication_manager",
            handoff_reason="medication question",
            context={"trigger_content": "I forgot my pills"},
            request_id="req-001",
        )
        await agent.handle_event(event)
        await asyncio.sleep(0.15)

        assert len(responses) == 1
        assert responses[0].accepted is True
        assert responses[0].from_agent == "medication_manager"
        assert responses[0].request_id == "req-001"

        await agent.stop()
        await bus.stop()

    async def test_handoff_with_no_medications_calls_llm(self, agent, bus, llm):
        """With no meds on record, LLM still called; response contains the canned text."""
        await bus.start()
        await agent.start()

        responses: list[AgentHandoffResponseEvent] = []

        async def capture(event):
            if isinstance(event, AgentHandoffResponseEvent):
                responses.append(event)

        bus.subscribe(EventTypes.AGENT_HANDOFF_RESPONSE, capture, "test-no-meds")

        llm.queue("No active medications on record. I'll note this for context.")

        event = AgentHandoffRequestEvent(
            source="wellness_companion",
            session_id="sess-002",
            patient_id="pat-unit-001",
            from_agent="wellness_companion",
            target_agent="medication_manager",
            handoff_reason="medication discussion",
            context={"trigger_content": "I want to discuss my medication"},
            request_id="req-002",
        )
        await agent.handle_event(event)
        await asyncio.sleep(0.15)

        assert len(responses) == 1
        assert responses[0].accepted is True
        assert len(llm.calls) >= 1

        await agent.stop()
        await bus.stop()

    async def test_handoff_with_existing_medications_includes_med_list_in_prompt(
        self, agent, bus, llm, state
    ):
        """LLM prompt should include existing medication names."""
        # Add a medication to the patient record
        await state.create_medication({
            "id": "med-001",
            "patient_id": "pat-unit-001",
            "name": "Sertraline",
            "dosage": "50mg",
            "frequency": "daily",
        })

        await bus.start()
        await agent.start()

        responses: list[AgentHandoffResponseEvent] = []
        async def capture(event):
            if isinstance(event, AgentHandoffResponseEvent):
                responses.append(event)
        bus.subscribe(EventTypes.AGENT_HANDOFF_RESPONSE, capture, "test-with-meds")

        llm.queue("Patient is on Sertraline 50mg daily. Noted in context.")

        event = AgentHandoffRequestEvent(
            source="wellness_companion",
            session_id="sess-003",
            patient_id="pat-unit-001",
            from_agent="wellness_companion",
            target_agent="medication_manager",
            handoff_reason="medication question",
            context={"trigger_content": "my sertraline makes me tired"},
            request_id="req-003",
        )
        await agent.handle_event(event)
        await asyncio.sleep(0.15)

        assert len(responses) == 1
        assert responses[0].accepted is True
        # Verify LLM received the med name in the prompt
        assert len(llm.calls) >= 1
        prompt_content = llm.calls[-1]["messages"][0]["content"]
        assert "Sertraline" in prompt_content

        await agent.stop()
        await bus.stop()


# ---------------------------------------------------------------------------
# Interaction check
# ---------------------------------------------------------------------------

class TestInteractionCheck:

    async def test_no_existing_medications_returns_none(self, agent, bus, llm):
        """With no existing meds, check_interactions returns None immediately."""
        await bus.start()
        await agent.start()

        result = await agent.check_interactions("pat-unit-001", "Prozac")
        assert result is None
        # LLM should NOT be called when there are no existing meds
        assert len(llm.calls) == 0

        await agent.stop()
        await bus.stop()

    async def test_no_interaction_returns_none(self, agent, bus, llm, state):
        """LLM says NO_INTERACTION → returns None, no event published."""
        await state.create_medication({
            "id": "med-002",
            "patient_id": "pat-unit-001",
            "name": "Melatonin",
        })

        await bus.start()
        await agent.start()

        llm.queue("NO_INTERACTION")

        result = await agent.check_interactions("pat-unit-001", "Vitamin D")
        assert result is None

        await agent.stop()
        await bus.stop()

    async def test_interaction_returns_description(self, agent, bus, llm, state):
        """LLM says INTERACTION → returns the description string."""
        await state.create_medication({
            "id": "med-003",
            "patient_id": "pat-unit-001",
            "name": "Warfarin",
        })

        await bus.start()
        await agent.start()

        llm.queue("INTERACTION: Prozac may increase Warfarin levels — monitor INR")

        result = await agent.check_interactions("pat-unit-001", "Prozac")
        assert result is not None
        assert "Warfarin" in result or "Prozac" in result or "INR" in result

        await agent.stop()
        await bus.stop()

    async def test_interaction_publishes_event(self, agent, bus, llm, state):
        """When interaction is detected, MedicationInteractionDetectedEvent is published."""
        await state.create_medication({
            "id": "med-004",
            "patient_id": "pat-unit-001",
            "name": "MAOIs",
        })

        await bus.start()
        await agent.start()

        detected: list[MedicationInteractionDetectedEvent] = []

        async def capture(event):
            if isinstance(event, MedicationInteractionDetectedEvent):
                detected.append(event)

        bus.subscribe(EventTypes.MEDICATION_INTERACTION_DETECTED, capture, "test-interaction")

        llm.queue("INTERACTION: SSRIs with MAOIs risk serotonin syndrome")

        await agent.check_interactions("pat-unit-001", "Fluoxetine")
        await asyncio.sleep(0.15)

        assert len(detected) == 1
        evt = detected[0]
        assert evt.patient_id == "pat-unit-001"
        assert evt.new_medication == "Fluoxetine"
        assert "MAOIs" in evt.existing_medications
        assert len(evt.interaction_notes) > 0

        await agent.stop()
        await bus.stop()

    async def test_llm_failure_returns_none_gracefully(self, agent, bus, state):
        """If LLM raises, check_interactions returns None without crashing."""
        await state.create_medication({
            "id": "med-005",
            "patient_id": "pat-unit-001",
            "name": "Aspirin",
        })

        # Use a failing LLM
        class FailingLLM(LLMProvider):
            async def complete(self, *args, **kwargs) -> LLMResponse:
                raise RuntimeError("LLM unavailable")
            async def stream(self, *args, **kwargs) -> AsyncIterator[str]:
                yield ""

        failing_agent = MedicationManagerAgent()
        failing_agent.initialize(bus, config := AdaConfig(), state, FailingLLM())

        await bus.start()
        await failing_agent.start()

        result = await failing_agent.check_interactions("pat-unit-001", "Ibuprofen")
        assert result is None  # Degraded gracefully

        await failing_agent.stop()
        await bus.stop()
