"""
Integration tests for the crisis detection pipeline.

Verifies that crisis-indicating messages published to the EventBus flow
through CrisisMonitorAgent and produce CrisisDetectedEvents with correct
severity, that alerts are persisted to SQLite, and that non-crisis
messages do not trigger alerts.

The LLM stage is exercised via a MockLLMProvider that returns canned
JSON responses simulating the LLM crisis assessment output.

@decision DEC-TEST-006
@title Crisis pipeline integration tests use MockLLMProvider with canned JSON
@status accepted
@rationale The CrisisMonitorAgent's LLM stage expects a specific JSON
    structure from the provider. The MockLLMProvider returns valid JSON
    strings so the full two-stage pipeline (keyword scan + LLM analysis)
    runs as it would in production. Only the HTTP boundary to the real
    LLM API is avoided.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ada.agents.crisis_monitor import CrisisMonitorAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    CrisisDetectedEvent,
    EventTypes,
    MessageReceivedEvent,
)
from ada.core.state import StateManager

from .conftest import MockLLMProvider


# ---------------------------------------------------------------------------
# LLM response helpers
# ---------------------------------------------------------------------------

def _llm_crisis_json(severity: str, reasoning: str = "test", confidence: str = "high") -> str:
    """Build the JSON string that CrisisMonitorAgent._llm_analyse() expects."""
    return json.dumps({
        "severity": severity,
        "reasoning": reasoning,
        "confidence": confidence,
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def crisis_agent(bus, config, state, llm, patient_id, session_id):
    """Fully wired, started CrisisMonitorAgent."""
    agent = CrisisMonitorAgent()
    agent.initialize(bus, config, state, llm)
    await bus.start()
    await agent.start()
    yield agent
    await agent.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# CRITICAL keyword path
# ---------------------------------------------------------------------------

class TestCriticalKeywordDetection:

    async def test_suicide_keyword_triggers_critical_alert(
        self, crisis_agent, bus, session_id, patient_id
    ):
        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "crisis-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I am thinking about suicide.",
            message_id="msg-crisis-001",
        ))
        await asyncio.sleep(0.4)

        assert len(detected) == 1
        assert detected[0].severity == "CRITICAL"
        assert detected[0].detection_method == "keyword"

    async def test_kill_myself_triggers_critical(
        self, crisis_agent, bus, session_id, patient_id
    ):
        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "crisis-capture-2")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I want to kill myself right now.",
            message_id="msg-crisis-002",
        ))
        await asyncio.sleep(0.4)

        assert len(detected) == 1
        assert detected[0].severity == "CRITICAL"

    async def test_critical_alert_persisted_to_state(
        self, crisis_agent, bus, state, session_id, patient_id
    ):
        """CRITICAL alerts must be saved to the crisis_alerts table."""
        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I want to end my life.",
            message_id="msg-persist-001",
        ))
        await asyncio.sleep(0.4)

        alerts = await state.get_crisis_alerts(patient_id)
        assert len(alerts) >= 1
        assert any(a["severity"] == "CRITICAL" for a in alerts)

    async def test_critical_escalation_action_contains_resources(
        self, crisis_agent, bus, session_id, patient_id
    ):
        """CRITICAL CrisisDetectedEvent should have crisis resource info."""
        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "crisis-escalation-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I took an overdose last night.",
            message_id="msg-overdose-001",
        ))
        await asyncio.sleep(0.4)

        assert len(detected) == 1
        action = detected[0].escalation_action
        assert "988" in action or "crisis" in action.lower() or "immediate" in action.lower()


# ---------------------------------------------------------------------------
# HIGH keyword path
# ---------------------------------------------------------------------------

class TestHighKeywordDetection:

    async def test_hopeless_triggers_high_alert(
        self, crisis_agent, bus, session_id, patient_id
    ):
        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "high-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="Everything feels completely hopeless.",
            message_id="msg-high-001",
        ))
        await asyncio.sleep(0.4)

        assert len(detected) == 1
        assert detected[0].severity == "HIGH"
        assert detected[0].detection_method == "keyword"


# ---------------------------------------------------------------------------
# LLM stage (MODERATE/LOW messages that pass to LLM)
# ---------------------------------------------------------------------------

class TestLLMStagePipeline:

    async def test_llm_critical_overrides_low_keyword(
        self, bus, config, state, patient_id, session_id
    ):
        """
        When keyword scan returns LOW but LLM returns CRITICAL,
        the final severity should be CRITICAL (safety-first).
        """
        llm = MockLLMProvider()
        llm.queue_response(_llm_crisis_json("CRITICAL", "Implicit suicidal ideation detected"))

        agent = CrisisMonitorAgent()
        agent.initialize(bus, config, state, llm)
        await bus.start()
        await agent.start()

        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "llm-override-capture")

        # "numb" triggers LOW keyword scan, then LLM is called
        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I just feel numb and empty all the time.",
            message_id="msg-llm-001",
        ))
        await asyncio.sleep(0.4)

        await agent.stop()
        await bus.stop()

        assert len(detected) == 1
        assert detected[0].severity == "CRITICAL"
        assert detected[0].detection_method == "llm"

    async def test_llm_none_response_does_not_raise_alert(
        self, bus, config, state, patient_id, session_id
    ):
        """LLM returning NONE severity should not produce a CrisisDetectedEvent."""
        llm = MockLLMProvider()
        llm.queue_response(_llm_crisis_json("NONE", "No crisis detected"))

        agent = CrisisMonitorAgent()
        agent.initialize(bus, config, state, llm)
        await bus.start()
        await agent.start()

        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "none-capture")

        # "feel" triggers emotional language heuristic -> LLM called
        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I feel a bit low energy today.",
            message_id="msg-llm-none-001",
        ))
        await asyncio.sleep(0.4)

        await agent.stop()
        await bus.stop()

        assert len(detected) == 0

    async def test_severity_always_escalates_not_deescalates(
        self, bus, config, state, patient_id, session_id
    ):
        """
        When keyword scan finds MODERATE and LLM returns HIGH,
        the final severity should be HIGH (higher wins, safety-first).
        """
        llm = MockLLMProvider()
        llm.queue_response(_llm_crisis_json("HIGH"))

        agent = CrisisMonitorAgent()
        agent.initialize(bus, config, state, llm)
        await bus.start()
        await agent.start()

        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "escalation-capture")

        # "trapped" is MODERATE keyword
        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I feel completely trapped and there's no way out.",
            message_id="msg-escalate-001",
        ))
        await asyncio.sleep(0.4)

        await agent.stop()
        await bus.stop()

        assert len(detected) == 1
        assert detected[0].severity == "HIGH"


# ---------------------------------------------------------------------------
# Non-crisis messages pass through cleanly
# ---------------------------------------------------------------------------

class TestNonCrisisMessages:

    async def test_benign_message_no_alert(
        self, crisis_agent, bus, session_id, patient_id
    ):
        """A clearly benign message should not trigger any CrisisDetectedEvent."""
        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "benign-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I had a great day at work today!",
            message_id="msg-benign-001",
        ))
        await asyncio.sleep(0.4)

        assert len(detected) == 0

    async def test_empty_message_no_alert(
        self, crisis_agent, bus, session_id, patient_id
    ):
        """An empty message should not trigger any alert."""
        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "empty-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="",
            message_id="msg-empty-001",
        ))
        await asyncio.sleep(0.4)

        assert len(detected) == 0

    async def test_multiple_benign_messages_no_alerts(
        self, crisis_agent, bus, state, session_id, patient_id
    ):
        """Multiple benign messages should produce zero crisis alerts in state."""
        for i, text in enumerate([
            "How does CBT work?",
            "I want to understand anxiety better.",
            "What is mindfulness?",
        ]):
            await bus.publish(MessageReceivedEvent(
                session_id=session_id,
                patient_id=patient_id,
                content=text,
                message_id=f"msg-benign-{i}",
            ))

        await asyncio.sleep(0.4)

        alerts = await state.get_crisis_alerts(patient_id)
        assert len(alerts) == 0

    async def test_crisis_event_has_correct_patient_and_session(
        self, crisis_agent, bus, session_id, patient_id
    ):
        """The CrisisDetectedEvent should carry the correct session/patient IDs."""
        detected: list[CrisisDetectedEvent] = []

        async def capture(event):
            detected.append(event)

        bus.subscribe(EventTypes.CRISIS_DETECTED, capture, "id-check-capture")

        await bus.publish(MessageReceivedEvent(
            session_id=session_id,
            patient_id=patient_id,
            content="I want to kill myself.",
            message_id="msg-id-check-001",
        ))
        await asyncio.sleep(0.4)

        assert len(detected) == 1
        assert detected[0].session_id == session_id
        assert detected[0].patient_id == patient_id
        assert detected[0].trigger_text != ""
