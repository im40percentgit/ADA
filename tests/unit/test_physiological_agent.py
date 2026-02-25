"""
Unit tests for PhysiologicalAgent.

Tests the sliding window logic, trigger interval, and LLM classification
pipeline. Uses real EventBus and in-memory SQLite.

@decision DEC-ML-014
@title PhysiologicalAgent tests verify sliding window trigger behavior
@status accepted
@rationale The key behavior to test is: readings accumulate in the window,
    classification triggers after trigger_interval readings, and alerts
    produce SensorAlertEvents. Window size and trigger interval are
    configurable via MultimodalConfig.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import pytest
import pytest_asyncio

from ada.agents.physiological import PhysiologicalAgent
from ada.core.bus import EventBus
from ada.core.config import AdaConfig
from ada.core.events import (
    EventTypes,
    SensorAlertEvent,
    SensorReadingEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider, LLMResponse


# ---------------------------------------------------------------------------
# MockLLMProvider
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    def __init__(self, default_response: str = "{}") -> None:
        self.default_response = default_response
        self.response_queue: list[str] = []
        self.calls: list[dict] = []

    def queue_response(self, response: str) -> None:
        self.response_queue.append(response)

    async def complete(
        self, messages: list[dict], *, max_tokens: int = 1024,
        temperature: float = 0.7, system: str | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "system": system})
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        return LLMResponse(content=content, model="mock", input_tokens=1, output_tokens=1)

    async def stream(
        self, messages: list[dict], *, max_tokens: int = 1024,
        temperature: float = 0.7, system: str | None = None,
    ) -> AsyncIterator[str]:
        content = self.response_queue.pop(0) if self.response_queue else self.default_response
        for word in content.split():
            yield word + " "


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canned_physio_json(
    stress_level: str = "moderate",
    arousal: float = 0.6,
    alerts: list | None = None,
) -> str:
    return json.dumps({
        "stress_level": stress_level,
        "arousal": arousal,
        "alerts": alerts or [],
        "reasoning": "Moderate HR elevation with stable GSR",
    })


def _canned_physio_with_alert() -> str:
    return json.dumps({
        "stress_level": "high",
        "arousal": 0.85,
        "alerts": [
            {"type": "hr_spike", "description": "Heart rate jumped 30bpm in 10s"},
            {"type": "gsr_spike", "description": "GSR doubled"},
        ],
        "reasoning": "Sudden physiological arousal spike",
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def state():
    sm = StateManager(":memory:")
    await sm.initialize()
    await sm.create_patient({
        "id": "patient-001", "name": "Test Patient",
        "dob": None, "preferences": {}, "emergency_contact": None,
        "caregiver_id": None,
    })
    await sm.create_session({"id": "session-001", "patient_id": "patient-001"})
    yield sm
    await sm.close()


@pytest_asyncio.fixture
async def agent_setup(state):
    bus = EventBus()
    await bus.start()
    llm = MockLLMProvider()
    config = AdaConfig()
    agent = PhysiologicalAgent()
    agent.initialize(bus, config, state, llm)
    await agent.start()
    yield agent, bus, llm, state
    await agent.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPhysiologicalAgent:
    @pytest.mark.asyncio
    async def test_no_classification_before_trigger_interval(self, agent_setup):
        """Should not call LLM until trigger_interval readings received."""
        agent, bus, llm, state = agent_setup

        # Send 9 readings (default trigger is 10)
        for i in range(9):
            await bus.publish(SensorReadingEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                sensor_type="hr",
                value=70.0 + i,
                unit="bpm",
            ))
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.1)
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_classification_triggers_at_interval(self, agent_setup):
        """LLM should be called after trigger_interval readings."""
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_physio_json())

        # Send 10 readings (trigger_interval=10)
        for i in range(10):
            await bus.publish(SensorReadingEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                sensor_type="hr",
                value=70.0 + i,
                unit="bpm",
            ))
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.2)
        assert len(llm.calls) == 1

    @pytest.mark.asyncio
    async def test_alerts_produce_sensor_alert_events(self, agent_setup):
        """SensorAlertEvents should be published when LLM returns alerts."""
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_physio_with_alert())

        received: list[SensorAlertEvent] = []

        async def collector(event):
            received.append(event)

        bus.subscribe(EventTypes.SENSOR_ALERT, collector, "alert-collector")

        # Send 10 readings to trigger classification
        for i in range(10):
            await bus.publish(SensorReadingEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                sensor_type="hr",
                value=80.0 + i * 3,  # Rising heart rate
                unit="bpm",
            ))
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.3)

        assert len(received) == 2
        alert_types = {a.alert_type for a in received}
        assert "hr_spike" in alert_types
        assert "gsr_spike" in alert_types
        assert all(a.session_id == "session-001" for a in received)

    @pytest.mark.asyncio
    async def test_multiple_sensor_types_in_window(self, agent_setup):
        """Window should track multiple sensor types independently."""
        agent, bus, llm, state = agent_setup
        llm.queue_response(_canned_physio_json())

        # Send mixed sensor readings
        for i in range(4):
            for sensor, val, unit in [("hr", 70.0, "bpm"), ("gsr", 3.0, "uS"), ("spo2", 98.0, "%")]:
                await bus.publish(SensorReadingEvent(
                    source="test",
                    session_id="session-001",
                    patient_id="patient-001",
                    sensor_type=sensor,
                    value=val + i,
                    unit=unit,
                ))
                await asyncio.sleep(0.01)

        # 4 iterations * 3 sensors = 12 readings, should trigger (>=10)
        await asyncio.sleep(0.2)

        assert len(llm.calls) == 1
        # Verify prompt contains all sensor types
        prompt = llm.calls[0]["messages"][0]["content"]
        assert "HR" in prompt
        assert "GSR" in prompt
        assert "SPO2" in prompt

    @pytest.mark.asyncio
    async def test_empty_session_id_skipped(self, agent_setup):
        agent, bus, llm, state = agent_setup

        await bus.publish(SensorReadingEvent(
            source="test",
            session_id="",
            patient_id="patient-001",
            sensor_type="hr",
            value=70.0,
            unit="bpm",
        ))

        await asyncio.sleep(0.1)
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_invalid_json_skips(self, agent_setup):
        """Bad LLM response should not produce alerts."""
        agent, bus, llm, state = agent_setup
        llm.queue_response("not json")

        received: list = []
        bus.subscribe(EventTypes.SENSOR_ALERT, lambda e: received.append(e), "bad-json")

        for i in range(10):
            await bus.publish(SensorReadingEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                sensor_type="hr",
                value=70.0,
                unit="bpm",
            ))
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.2)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_agent_properties(self):
        agent = PhysiologicalAgent()
        assert agent.name == "physiological"
        assert "physiological" in agent.description.lower()
        assert EventTypes.SENSOR_READING in agent.supported_events

    @pytest.mark.asyncio
    async def test_stop_clears_windows(self, agent_setup):
        agent, bus, llm, state = agent_setup

        # Add some readings
        for i in range(5):
            await bus.publish(SensorReadingEvent(
                source="test",
                session_id="session-001",
                patient_id="patient-001",
                sensor_type="hr",
                value=70.0,
                unit="bpm",
            ))
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.1)
        assert len(agent._windows) > 0

        await agent.stop()
        assert len(agent._windows) == 0
        assert len(agent._counters) == 0
