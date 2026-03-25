"""
PhysiologicalAgent -- sliding window analysis of sensor data + LLM classification.

Subscribes to SENSOR_READING, maintains per-session sliding windows of
sensor values, and triggers LLM classification every N readings. Publishes
SensorAlertEvent when anomalies are detected.

@decision DEC-ML-003
@title Three independent agents, fusion deferred
@status accepted
@rationale PhysiologicalAgent produces stress/arousal signals independently.
    MultimodalFusionAgent (combining all signals) is deferred to Phase 4c.

@decision DEC-ML-013
@title Sliding window with configurable trigger interval
@status accepted
@rationale Sensor readings arrive at ~1Hz. Classifying every reading would
    waste LLM calls. A sliding window of 30 readings with a trigger every
    10 new readings gives the LLM trend context while controlling cost.
    Both window_size and trigger_interval are configurable via MultimodalConfig.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import deque

import numpy as np

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    EventTypes,
    SensorAlertEvent,
    SensorReadingEvent,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a physiological stress analysis module for a mental health support system.
Analyse the physiological data window from a therapy session and classify
the patient's stress and arousal levels.

Respond ONLY with a valid JSON object -- no prose, no markdown fences:
{
  "stress_level": "<low|moderate|high|critical>",
  "arousal": <0.0-1.0>,
  "alerts": [{"type": "<hr_spike|gsr_spike|spo2_drop|rapid_change>", "description": "..."}],
  "reasoning": "<brief explanation>"
}"""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap JSON in."""
    text = re.sub(r'^\s*```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?\s*```\s*$', '', text)
    return text.strip()


class PhysiologicalAgent(BaseAgent):
    """
    Physiological stress analysis agent.

    Maintains per-session sliding windows of sensor readings (hr, gsr, spo2).
    Every trigger_interval new readings, sends the window to the LLM for
    stress classification. Publishes SensorAlertEvent for any detected anomalies.
    """

    def __init__(self) -> None:
        super().__init__()
        # session_id -> sensor_type -> deque of values
        self._windows: dict[str, dict[str, deque[float]]] = {}
        # session_id -> count of readings since last trigger
        self._counters: dict[str, int] = {}

    @property
    def name(self) -> str:
        return "physiological"

    @property
    def description(self) -> str:
        return "Physiological agent -- sliding window stress analysis via LLM"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.SENSOR_READING]

    @property
    def _window_size(self) -> int:
        if self._config and hasattr(self._config, "multimodal"):
            return getattr(self._config.multimodal, "physiological_window_size", 30)
        return 30

    @property
    def _trigger_interval(self) -> int:
        if self._config and hasattr(self._config, "multimodal"):
            return getattr(self._config.multimodal, "physiological_trigger_interval", 10)
        return 10

    async def handle_event(self, event: AdaEvent) -> None:
        """Route incoming events to typed handlers."""
        try:
            if event.event_type == EventTypes.SENSOR_READING:
                assert isinstance(event, SensorReadingEvent)
                await self._handle_sensor_reading(event)
        except Exception:
            logger.exception("PhysiologicalAgent: unhandled error in handle_event")

    async def _handle_sensor_reading(self, event: SensorReadingEvent) -> None:
        """Add reading to sliding window, trigger classification if interval reached."""
        sid = event.session_id
        if not sid:
            return

        # Initialize window for this session if needed
        if sid not in self._windows:
            self._windows[sid] = {}
            self._counters[sid] = 0

        # Add to sliding window
        sensor = event.sensor_type
        if sensor not in self._windows[sid]:
            self._windows[sid][sensor] = deque(maxlen=self._window_size)

        self._windows[sid][sensor].append(event.value)
        self._counters[sid] += 1

        # Check if we should trigger classification
        if self._counters[sid] >= self._trigger_interval:
            self._counters[sid] = 0
            await self._classify_window(
                session_id=sid,
                patient_id=event.patient_id,
            )

    async def _classify_window(self, *, session_id: str, patient_id: str) -> None:
        """Send current window to LLM for stress classification."""
        windows = self._windows.get(session_id, {})
        if not windows:
            return

        # Build prompt with window data
        prompt_parts = []
        for sensor_type, values in windows.items():
            vals = list(values)
            if not vals:
                continue
            arr = np.array(vals)
            mean_val = float(np.mean(arr))
            delta = float(arr[-1] - arr[0]) if len(arr) > 1 else 0.0
            min_val = float(np.min(arr))
            max_val = float(np.max(arr))

            unit = {"hr": "bpm", "gsr": "uS", "spo2": "%"}.get(sensor_type, "")
            prompt_parts.append(
                f"{sensor_type.upper()} trend: last {len(vals)} readings, "
                f"mean={mean_val:.1f}{unit}, delta={delta:+.1f}, "
                f"min={min_val:.1f}, max={max_val:.1f}"
            )

        if not prompt_parts:
            return

        prompt = "Analyse this physiological data window from a therapy session:\n"
        prompt += "\n".join(f"- {p}" for p in prompt_parts)

        # LLM classification — bounded by config timeout
        try:
            response = await asyncio.wait_for(
                self.llm.complete(
                    [{"role": "user", "content": prompt}],
                    system=_SYSTEM_PROMPT,
                    max_tokens=256,
                    temperature=0.2,
                ),
                timeout=self.config.llm.timeout,
            )
            raw = response.content
        except Exception:
            logger.exception(
                "PhysiologicalAgent: LLM call failed for session %s", session_id,
            )
            return

        # Parse response
        try:
            cleaned = _strip_fences(raw)
            data = json.loads(cleaned)
            stress_level = str(data["stress_level"])
            arousal = float(data["arousal"])
            alerts = data.get("alerts", [])
        except Exception:
            logger.warning(
                "PhysiologicalAgent: failed to parse LLM response for "
                "session %s -- raw=%r",
                session_id, raw,
            )
            return

        # Publish alerts
        for alert in alerts:
            alert_type = alert.get("type", "unknown")
            description = alert.get("description", "")
            await self.bus.publish(
                SensorAlertEvent(
                    source=self.name,
                    session_id=session_id,
                    patient_id=patient_id,
                    sensor_type=alert_type.split("_")[0] if "_" in alert_type else "multi",
                    alert_type=alert_type,
                    value=arousal,
                    threshold=0.0,
                    description=f"stress={stress_level}, {description}",
                )
            )

        logger.info(
            "PhysiologicalAgent: session=%s stress=%s arousal=%.2f alerts=%d",
            session_id, stress_level, arousal, len(alerts),
        )

    async def stop(self) -> None:
        """Clean up windows on stop."""
        self._windows.clear()
        self._counters.clear()
        await super().stop()
