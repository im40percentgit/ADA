"""
Sensor simulator for generating realistic physiological data streams.

Produces SENSOR_READING events via EventBus with configurable presets
modelling different emotional/physiological states. Swappable for real
IoT gateway without changing any consumer code.

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
import random
from dataclasses import dataclass

from ada.core.bus import EventBus
from ada.core.events import EventTypes, SensorReadingEvent


@dataclass
class SensorPreset:
    """Value ranges for a single sensor type within a preset."""

    mean: float
    std: float
    min_val: float
    max_val: float
    unit: str


# Clinically-plausible ranges based on published stress response data
_PRESETS: dict[str, dict[str, SensorPreset]] = {
    "relaxed": {
        "hr": SensorPreset(mean=68.0, std=4.0, min_val=55.0, max_val=85.0, unit="bpm"),
        "gsr": SensorPreset(mean=2.0, std=0.3, min_val=1.0, max_val=4.0, unit="uS"),
        "spo2": SensorPreset(mean=98.0, std=0.5, min_val=96.0, max_val=100.0, unit="%"),
    },
    "anxious": {
        "hr": SensorPreset(mean=88.0, std=6.0, min_val=75.0, max_val=110.0, unit="bpm"),
        "gsr": SensorPreset(mean=5.0, std=1.0, min_val=3.0, max_val=10.0, unit="uS"),
        "spo2": SensorPreset(mean=97.0, std=0.8, min_val=94.0, max_val=99.0, unit="%"),
    },
    "panic_attack": {
        "hr": SensorPreset(mean=125.0, std=10.0, min_val=100.0, max_val=160.0, unit="bpm"),
        "gsr": SensorPreset(mean=10.0, std=2.0, min_val=6.0, max_val=18.0, unit="uS"),
        "spo2": SensorPreset(mean=95.0, std=1.5, min_val=90.0, max_val=98.0, unit="%"),
    },
}


class SensorSimulator:
    """Generates realistic physiological sensor data streams.

    Usage:
        sim = SensorSimulator(bus=event_bus)
        await sim.generate_stream(session_id, patient_id, preset="relaxed", num_readings=100)
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._running = False

    @property
    def presets(self) -> dict[str, dict[str, SensorPreset]]:
        """Return available preset configurations."""
        return _PRESETS

    async def emit_reading(
        self, *, session_id: str, patient_id: str,
        sensor_type: str, value: float, unit: str,
    ) -> None:
        """Publish a single sensor reading event."""
        if self._bus is None:
            raise RuntimeError("SensorSimulator requires an EventBus")
        await self._bus.publish(
            SensorReadingEvent(
                source="sensor_simulator",
                session_id=session_id,
                patient_id=patient_id,
                sensor_type=sensor_type,
                value=round(value, 1),
                unit=unit,
            )
        )

    async def generate_stream(
        self, *, session_id: str, patient_id: str,
        preset: str = "relaxed", num_readings: int = 100,
        interval_s: float = 1.0,
    ) -> None:
        """Generate a stream of sensor readings from a named preset.

        Emits one reading per sensor type per interval tick. With 3 sensor
        types (hr, gsr, spo2), each tick produces 3 SENSOR_READING events.

        Args:
            session_id: Active session identifier.
            patient_id: Patient identifier.
            preset: Preset name -- one of 'relaxed', 'anxious', 'panic_attack'.
            num_readings: Number of ticks (each produces 3 events).
            interval_s: Sleep duration between ticks in seconds.
        """
        if preset not in _PRESETS:
            raise ValueError(
                f"Unknown preset: {preset!r}. Choose from {list(_PRESETS.keys())}"
            )

        self._running = True
        preset_config = _PRESETS[preset]

        for _ in range(num_readings):
            if not self._running:
                break

            for sensor_type, sp in preset_config.items():
                value = random.gauss(sp.mean, sp.std)
                value = max(sp.min_val, min(sp.max_val, value))
                await self.emit_reading(
                    session_id=session_id,
                    patient_id=patient_id,
                    sensor_type=sensor_type,
                    value=value,
                    unit=sp.unit,
                )

            await asyncio.sleep(interval_s)

    def stop(self) -> None:
        """Signal the current stream generation to stop after the current tick."""
        self._running = False
