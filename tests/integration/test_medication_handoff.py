"""
Integration test — full medication handoff flow with real MedicationManagerAgent.

Unlike test_handoff_flow.py (which uses a MockMedicationAgent stub), this test
wires the real MedicationManagerAgent into the EventBus alongside WellnessCompanionAgent
to verify the complete end-to-end pipeline:

  1. User message with medication keyword → WellnessCompanionAgent publishes AGENT_HANDOFF_REQUEST
  2. MedicationManagerAgent receives it (target_agent="medication_manager")
  3. MedicationManagerAgent loads patient medications, queries LLM, publishes response
  4. WellnessCompanionAgent receives AGENT_HANDOFF_RESPONSE

All state is in-memory SQLite. MockLLMProvider stands in for external LLM API.

@decision DEC-AGENT-004
@title Integration test wires real MedicationManagerAgent on shared EventBus
@status accepted
@rationale The existing test_handoff_flow.py proves the protocol using a stub.
    This test proves the real agent implementation — including state access and
    LLM prompting — works within the full event-driven pipeline. Both are
    needed: stub tests catch protocol regressions; real-agent tests catch
    implementation regressions.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from ada.agents.medication_manager import MedicationManagerAgent
from ada.agents.wellness_companion import WellnessCompanionAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    AgentHandoffRequestEvent,
    AgentHandoffResponseEvent,
    EventTypes,
    MessageReceivedEvent,
    MedicationInteractionDetectedEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """Deterministic LLM stub with a per-call response queue."""

    def __init__(self, default_response: str = "Noted in context.") -> None:
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
        "id": "pat-integ-med",
        "name": "Integration Med Patient",
        "dob": None,
        "preferences": {},
        "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({
        "id": "sess-integ-med",
        "patient_id": "pat-integ-med",
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
def therapist(bus, config, state, llm) -> WellnessCompanionAgent:
    agent = WellnessCompanionAgent()
    agent.initialize(bus, config, state, llm)
    return agent


@pytest.fixture
def med_agent(bus, config, state, llm) -> MedicationManagerAgent:
    agent = MedicationManagerAgent()
    agent.initialize(bus, config, state, llm)
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRealMedicationHandoffFlow:

    async def test_medication_keyword_triggers_real_agent_handoff(
        self, therapist, med_agent, bus, state, llm
    ):
        """Full flow: medication keyword → WellnessCompanionAgent → real MedicationManagerAgent → response."""
        await bus.start()
        await therapist.start()
        await med_agent.start()

        responses: list[AgentHandoffResponseEvent] = []

        async def capture_responses(event):
            if isinstance(event, AgentHandoffResponseEvent):
                responses.append(event)

        bus.subscribe(EventTypes.AGENT_HANDOFF_RESPONSE, capture_responses, "integ-resp")

        # Queue LLM responses: first for the med manager handoff, second for therapist reply
        llm.queue("Patient has no active medications on record. Encouraging discussion noted.")
        llm.queue("I hear you — it's important to keep track of your medications.")

        event = MessageReceivedEvent(
            session_id="sess-integ-med",
            patient_id="pat-integ-med",
            content="I forgot to take my medication this morning",
            message_id="msg-integ-001",
        )
        await therapist.handle_event(event)
        await asyncio.sleep(0.3)

        assert len(responses) >= 1
        resp = responses[0]
        assert resp.from_agent == "medication_manager"
        assert resp.accepted is True
        assert len(resp.notes) > 0

        await therapist.stop()
        await med_agent.stop()
        await bus.stop()

    async def test_real_agent_includes_existing_meds_in_notes(
        self, therapist, med_agent, bus, state, llm
    ):
        """MedicationManagerAgent should query patient meds and include them in LLM prompt."""
        # Pre-seed a medication
        await state.create_medication({
            "id": "med-integ-001",
            "patient_id": "pat-integ-med",
            "name": "Sertraline",
            "dosage": "100mg",
            "frequency": "once daily",
        })

        await bus.start()
        await therapist.start()
        await med_agent.start()

        # Capture LLM calls to verify the med name is in the prompt
        llm.queue("Patient is currently on Sertraline 100mg once daily.")
        llm.queue("I understand you want to discuss your Sertraline.")

        event = MessageReceivedEvent(
            session_id="sess-integ-med",
            patient_id="pat-integ-med",
            content="My prescription is running low",
            message_id="msg-integ-002",
        )
        await therapist.handle_event(event)
        await asyncio.sleep(0.3)

        # Find the LLM call that went to the med manager (system prompt contains "Medication Manager")
        med_calls = [
            c for c in llm.calls
            if c.get("system") and "Medication Manager" in c["system"]
        ]
        assert len(med_calls) >= 1
        # Verify Sertraline appears in the prompt content
        prompt_content = med_calls[0]["messages"][0]["content"]
        assert "Sertraline" in prompt_content

        await therapist.stop()
        await med_agent.stop()
        await bus.stop()

    async def test_interaction_check_via_real_agent_and_state(
        self, med_agent, bus, state, llm
    ):
        """Real agent's check_interactions() loads from state and calls LLM."""
        await state.create_medication({
            "id": "med-integ-002",
            "patient_id": "pat-integ-med",
            "name": "Warfarin",
        })

        await bus.start()
        await med_agent.start()

        interaction_events: list[MedicationInteractionDetectedEvent] = []

        async def capture(event):
            if isinstance(event, MedicationInteractionDetectedEvent):
                interaction_events.append(event)

        bus.subscribe(EventTypes.MEDICATION_INTERACTION_DETECTED, capture, "integ-interaction")

        llm.queue("INTERACTION: Aspirin increases bleeding risk with Warfarin")

        result = await med_agent.check_interactions("pat-integ-med", "Aspirin")
        await asyncio.sleep(0.15)

        assert result is not None
        assert "bleeding" in result.lower() or "Warfarin" in result or "Aspirin" in result

        assert len(interaction_events) == 1
        evt = interaction_events[0]
        assert evt.patient_id == "pat-integ-med"
        assert evt.new_medication == "Aspirin"
        assert "Warfarin" in evt.existing_medications

        await med_agent.stop()
        await bus.stop()

    async def test_no_interaction_for_clean_combination(
        self, med_agent, bus, state, llm
    ):
        """check_interactions returns None when LLM says NO_INTERACTION."""
        await state.create_medication({
            "id": "med-integ-003",
            "patient_id": "pat-integ-med",
            "name": "Melatonin",
        })

        await bus.start()
        await med_agent.start()

        llm.queue("NO_INTERACTION")

        result = await med_agent.check_interactions("pat-integ-med", "Vitamin D")
        assert result is None

        await med_agent.stop()
        await bus.stop()
