"""
DailySummaryGenerator — generates caregiver-readable daily narratives at session end.

Listens for SESSION_ENDED events. On each event it:
  1. Starts (or restarts) a debounce timer for the patient.
  2. After the debounce delay (default 30 min), queries:
       - SOAP session summaries from the last 24 hours
       - Assessment scores from the last 7 days (for trend context)
       - Crisis alerts from the last 24 hours
       - Fused emotion signals from the last 24 hours
  3. Builds an LLM prompt with all aggregated context.
  4. Calls the LLM requesting structured JSON output.
  5. Parses the response (with regex code-fence stripping fallback).
  6. UPSERTs the DailySummary to the daily_summaries table.
  7. Publishes DAILY_SUMMARY_GENERATED.

If the LLM returns malformed JSON the generator logs a warning and skips —
daily summary generation is best-effort, not a hard requirement.

This is an infrastructure subscriber, NOT a BaseAgent subclass. It does not
participate in the AgentRegistry or respond to therapy events. It is
instantiated directly in main.py after registry.start_all(), following the
same pattern as SessionSummarizer.

@decision DEC-DAILY-001
@title DailySummaryGenerator as infrastructure subscriber with asyncio debounce
@status accepted
@rationale A patient may have multiple sessions in a day. Generating a daily
    summary after every session would produce partial summaries — the last
    session of the day hasn't happened yet. A 30-minute debounce (dict of
    asyncio.Tasks keyed by patient_id) waits for the "last" SESSION_ENDED
    before committing. If another session ends within 30 minutes the timer
    resets. This matches the simulator.py DEC-API-005 pattern and keeps the
    implementation simple with no external scheduler dependency.

@decision DEC-DAILY-002
@title Trend detection embedded in daily summary LLM prompt
@status accepted
@rationale Passing 7-day assessment scores directly in the LLM context window
    gives the model the raw material to identify trends (e.g., "PHQ-9 score
    has risen for 5 consecutive days") without a separate trend-detection
    component. This avoids a second LLM call and keeps the daily summary
    pipeline to a single round-trip. The trade-off (less precise algorithmic
    trend detection) is acceptable for a caregiver summary use case.

@decision DEC-DAILY-003
@title UPSERT via INSERT OR REPLACE with UNIQUE(patient_id, summary_date)
@status accepted
@rationale If the debounce fires, a summary is generated, and then the patient
    starts another session the same day, the timer resets and a new summary
    is generated. INSERT OR REPLACE ensures the latest summary wins without
    requiring application-layer deduplication logic. Matches DEC-SUMMARY-002.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from ada.core.bus import EventBus
from ada.core.events import (
    AdaEvent,
    DailySummaryGeneratedEvent,
    EventTypes,
    SessionEndedEvent,
)
from ada.core.state import StateManager
from ada.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_DAILY_SUMMARY_SYSTEM = """\
You are a caregiver support assistant. Given a day's wellness check-in summaries,
assessment scores, crisis alerts, and emotional signals, generate a daily
summary written for a family caregiver — not a clinician.

Write in warm, clear language. Avoid clinical jargon. Focus on:
1. How the person seemed today (overall mood, energy, engagement)
2. Any notable changes compared to recent days (trends)
3. Things the caregiver should mention at the next clinical appointment
4. Any concerning patterns that warrant attention

Respond with ONLY valid JSON — no markdown, no explanation:
{
  "narrative": "<2-3 sentence daily summary in plain language>",
  "trend_alerts": ["<alert if any concerning trend>"],
  "appointment_prep": ["<item to mention at next appointment>"],
  "key_topics": ["<topic 1>", "<topic 2>"],
  "overall_mood": "<one word: anxious/depressed/stable/improving/declining/mixed>"
}

Rules:
- narrative: plain language a non-medical person can understand
- trend_alerts: only include if there is a genuine multi-day pattern; use empty list [] if none
- appointment_prep: actionable items for the caregiver to bring up; use empty list [] if nothing notable
- key_topics: 1-5 main themes from today's check-in
- overall_mood: single word summarizing today's emotional state
"""

_DAILY_SUMMARY_USER = """\
Today's date: {today}

--- Session notes from today ---
{session_notes}

--- Assessment scores (last 7 days, newest first) ---
{assessment_scores}

--- Crisis alerts from today ---
{crisis_alerts}

--- Emotional signals from today ---
{emotion_signals}

Generate the daily summary JSON.
"""

# ---------------------------------------------------------------------------
# DailySummaryGenerator
# ---------------------------------------------------------------------------


class DailySummaryGenerator:
    """
    Infrastructure subscriber that generates caregiver daily narratives.

    Subscribes to SESSION_ENDED. Each event triggers a debounce timer for
    the patient. After the delay, aggregates context from the last 24 hours
    and calls the LLM to produce a caregiver-readable summary.

    Args:
        bus:              Running EventBus instance.
        state:            Initialised StateManager.
        llm:              LLM provider used for summary generation.
        debounce_seconds: Delay after last SESSION_ENDED before generating.
                          Default 1800 (30 min). Set low in tests.
    """

    def __init__(
        self,
        bus: EventBus,
        state: StateManager,
        llm: LLMProvider,
        debounce_seconds: float = 1800.0,
    ) -> None:
        self._bus = bus
        self._state = state
        self._llm = llm
        self._debounce_seconds = debounce_seconds
        self._pending: dict[str, asyncio.Task] = {}

        bus.subscribe(
            EventTypes.SESSION_ENDED,
            self._on_session_ended,
            "daily_summary_generator",
        )
        logger.info(
            "DailySummaryGenerator: subscribed to %s (debounce=%.0fs)",
            EventTypes.SESSION_ENDED,
            debounce_seconds,
        )

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    async def _on_session_ended(self, event: AdaEvent) -> None:
        """Handle SESSION_ENDED — cancel existing timer and start a new one."""
        if not isinstance(event, SessionEndedEvent):
            return

        patient_id = event.patient_id
        logger.info(
            "DailySummaryGenerator: SESSION_ENDED for patient %s — "
            "scheduling daily summary in %.0fs",
            patient_id,
            self._debounce_seconds,
        )

        # Cancel any existing pending task for this patient
        existing = self._pending.get(patient_id)
        if existing and not existing.done():
            existing.cancel()
            logger.debug(
                "DailySummaryGenerator: cancelled existing timer for patient %s",
                patient_id,
            )

        # Schedule new delayed task
        task = asyncio.create_task(
            self._delayed_generate(patient_id),
            name=f"daily_summary_{patient_id}",
        )
        self._pending[patient_id] = task

    # ------------------------------------------------------------------
    # Delayed generation
    # ------------------------------------------------------------------

    async def _delayed_generate(self, patient_id: str) -> None:
        """Wait for debounce delay then generate the daily summary."""
        try:
            await asyncio.sleep(self._debounce_seconds)
        except asyncio.CancelledError:
            logger.debug(
                "DailySummaryGenerator: timer cancelled for patient %s — "
                "another session ended; skipping",
                patient_id,
            )
            return

        try:
            await self._generate_daily_summary(patient_id)
        finally:
            # Clean up pending dict regardless of success/failure
            self._pending.pop(patient_id, None)

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    async def _generate_daily_summary(self, patient_id: str) -> None:
        """Aggregate context, call LLM, parse response, persist, and publish."""
        today = datetime.utcnow().date().isoformat()
        since_24h = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        since_7d = (datetime.utcnow() - timedelta(days=7)).isoformat()

        logger.info(
            "DailySummaryGenerator: generating daily summary for patient %s (date=%s)",
            patient_id,
            today,
        )

        # --- Gather context ---
        session_summaries = await self._state.get_session_summaries_for_patient(
            patient_id, since=since_24h
        )
        assessments = await self._state.get_assessments(patient_id)
        # Filter to last 7 days — get_assessments returns newest first
        recent_assessments = [
            a for a in assessments
            if a.get("timestamp", "") >= since_7d
        ]
        crisis_alerts = await self._state.get_crisis_alerts(patient_id)
        recent_alerts = [
            a for a in crisis_alerts
            if a.get("timestamp", "") >= since_24h
        ]
        fused_emotions = await self._state.get_fused_emotions_for_patient(
            patient_id, since=since_24h
        )

        # --- Build user prompt ---
        user_prompt = _DAILY_SUMMARY_USER.format(
            today=today,
            session_notes=_format_session_notes(session_summaries),
            assessment_scores=_format_assessments(recent_assessments),
            crisis_alerts=_format_alerts(recent_alerts),
            emotion_signals=_format_emotions(fused_emotions),
        )

        # --- Call LLM ---
        try:
            response = await self._llm.complete(
                messages=[{"role": "user", "content": user_prompt}],
                system=_DAILY_SUMMARY_SYSTEM,
                max_tokens=1024,
                temperature=0.3,
            )
        except Exception as exc:
            logger.warning(
                "DailySummaryGenerator: LLM call failed for patient %s: %s",
                patient_id,
                exc,
            )
            return

        # --- Parse response ---
        parsed = _parse_daily_summary_response(response.content)
        if parsed is None:
            logger.warning(
                "DailySummaryGenerator: failed to parse LLM response for patient %s",
                patient_id,
            )
            return

        # --- Persist ---
        summary_id = str(uuid.uuid4())
        record: dict[str, Any] = {
            "id": summary_id,
            "patient_id": patient_id,
            "summary_date": today,
            "narrative": str(parsed.get("narrative", "")),
            "trend_alerts": parsed.get("trend_alerts", []),
            "appointment_prep": parsed.get("appointment_prep", []),
            "key_topics": parsed.get("key_topics", []),
            "overall_mood": str(parsed.get("overall_mood", "stable")),
        }

        try:
            await self._state.create_or_update_daily_summary(record)
        except Exception as exc:
            logger.warning(
                "DailySummaryGenerator: failed to persist summary for patient %s: %s",
                patient_id,
                exc,
            )
            return

        # --- Publish ---
        await self._bus.publish(
            DailySummaryGeneratedEvent(
                source="daily_summary_generator",
                patient_id=patient_id,
                summary_id=summary_id,
                summary_date=today,
            )
        )
        logger.info(
            "DailySummaryGenerator: daily summary %s generated for patient %s (date=%s)",
            summary_id,
            patient_id,
            today,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Cancel all pending debounce tasks on shutdown."""
        for patient_id, task in list(self._pending.items()):
            if not task.done():
                task.cancel()
                logger.debug(
                    "DailySummaryGenerator: cancelled pending task for patient %s on shutdown",
                    patient_id,
                )
        self._pending.clear()
        logger.info("DailySummaryGenerator: shutdown complete")


# ---------------------------------------------------------------------------
# Helpers — context formatting
# ---------------------------------------------------------------------------


def _format_session_notes(summaries: list[dict[str, Any]]) -> str:
    """Format SOAP session summaries into readable text for the LLM prompt."""
    if not summaries:
        return "No session notes available for today."
    parts: list[str] = []
    for s in summaries:
        topics = ", ".join(s.get("key_topics", [])) or "none"
        parts.append(
            f"Subjective: {s.get('subjective', '')}\n"
            f"Assessment: {s.get('assessment', '')}\n"
            f"Plan: {s.get('plan', '')}\n"
            f"Key topics: {topics}"
        )
    return "\n\n---\n\n".join(parts)


def _format_assessments(assessments: list[dict[str, Any]]) -> str:
    """Format assessment results into readable text for the LLM prompt."""
    if not assessments:
        return "No assessment scores available."
    lines: list[str] = []
    for a in assessments:
        lines.append(
            f"{a.get('instrument', '').upper()} score {a.get('total_score', '?')} "
            f"({a.get('severity', '?')}) on {a.get('timestamp', '?')[:10]}"
        )
    return "\n".join(lines)


def _format_alerts(alerts: list[dict[str, Any]]) -> str:
    """Format crisis alerts into readable text for the LLM prompt."""
    if not alerts:
        return "No crisis alerts today."
    lines: list[str] = []
    for a in alerts:
        lines.append(
            f"Severity: {a.get('severity', '?')} at {a.get('timestamp', '?')[:16]}"
        )
    return "\n".join(lines)


def _format_emotions(emotions: list[dict[str, Any]]) -> str:
    """Format fused emotion records into readable text for the LLM prompt."""
    if not emotions:
        return "No emotional signal data available."
    lines: list[str] = []
    for e in emotions:
        modalities = ", ".join(e.get("modalities_available", [])) or "unknown"
        lines.append(
            f"Fused emotion: {e.get('fused_emotion', '?')} "
            f"(valence={e.get('fused_valence', 0):.2f}, "
            f"arousal={e.get('fused_arousal', 0):.2f}, "
            f"modalities: {modalities})"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers — JSON parsing
# ---------------------------------------------------------------------------


def _parse_daily_summary_response(raw: str) -> dict[str, Any] | None:
    """
    Parse the LLM daily summary response into a dict.

    Tries direct JSON parse first, then strips markdown code fences and
    retries. Returns None if both attempts fail.

    Follows the same pattern as SessionSummarizer._parse_soap_response()
    (DEC-SUMMARY-004).
    """
    # Attempt 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip markdown code fences
    stripped = re.sub(r"^\s*```(?:json)?\s*\n?", "", raw.strip(), flags=re.MULTILINE)
    stripped = re.sub(r"\n?\s*```\s*$", "", stripped, flags=re.MULTILINE)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    return None
