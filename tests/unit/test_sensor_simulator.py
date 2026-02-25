"""
Tests for SensorSimulator.

@decision DEC-MULTIMODAL-004
@title Simulated sensors first, real IoT gateway later
@status accepted
@rationale Proves the full data pipeline architecture without requiring
    physical hardware. Presets generate clinically-plausible ranges so
    downstream agents (PhysiologicalAgent, FusionAgent) can be tested
    under realistic conditions.
"""

from __future__ import annotations

import asyncio

import pytest

from ada.core.bus import EventBus
from ada.core.events import EventTypes, SensorReadingEvent
from ada.sensors.simulator import SensorSimulator


@pytest.fixture
async def bus():
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


class TestSensorSimulator:
    def test_default_presets(self):
        sim = SensorSimulator()
        assert "relaxed" in sim.presets
        assert "anxious" in sim.presets
        assert "panic_attack" in sim.presets

    def test_preset_has_all_sensor_types(self):
        sim = SensorSimulator()
        for preset_name, preset in sim.presets.items():
            assert "hr" in preset, f"Missing hr in {preset_name}"
            assert "gsr" in preset, f"Missing gsr in {preset_name}"
            assert "spo2" in preset, f"Missing spo2 in {preset_name}"

    async def test_generate_single_reading(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        await sim.emit_reading(
            session_id="s1", patient_id="p1",
            sensor_type="hr", value=72.0, unit="bpm",
        )
        await asyncio.sleep(0.05)

        assert len(collected) == 1
        assert collected[0].sensor_type == "hr"
        assert collected[0].value == 72.0

    async def test_generate_preset_stream(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        # Generate 3 readings at fast interval
        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="relaxed", num_readings=3, interval_s=0.05,
        )
        await asyncio.sleep(0.1)

        # 3 readings x 3 sensor types = 9 events
        assert len(collected) == 9
        sensor_types = {e.sensor_type for e in collected}
        assert sensor_types == {"hr", "gsr", "spo2"}

    async def test_relaxed_preset_ranges(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="relaxed", num_readings=10, interval_s=0.01,
        )
        await asyncio.sleep(0.2)

        hr_values = [e.value for e in collected if e.sensor_type == "hr"]
        for v in hr_values:
            assert 55 <= v <= 85, f"Relaxed HR {v} out of range"

    async def test_panic_preset_elevated(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        await sim.generate_stream(
            session_id="s1", patient_id="p1",
            preset="panic_attack", num_readings=10, interval_s=0.01,
        )
        await asyncio.sleep(0.2)

        hr_values = [e.value for e in collected if e.sensor_type == "hr"]
        for v in hr_values:
            assert v >= 100, f"Panic HR {v} too low"

    async def test_stop_stream(self, bus: EventBus):
        sim = SensorSimulator(bus=bus)
        collected: list[SensorReadingEvent] = []

        async def on_reading(event: SensorReadingEvent):
            collected.append(event)

        bus.subscribe(EventTypes.SENSOR_READING, on_reading, "test")

        task = asyncio.create_task(
            sim.generate_stream(
                session_id="s1", patient_id="p1",
                preset="relaxed", num_readings=1000, interval_s=0.01,
            )
        )
        await asyncio.sleep(0.05)
        sim.stop()
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have stopped early -- far fewer than 3000 events
        assert len(collected) < 100
