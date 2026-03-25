"""
SessionSummarizer — generates SOAP-format clinical notes at session end.

Listens for SESSION_ENDED events. On each event it:
  1. Fetches all messages for the session from StateManager.
  2. Builds a conversation transcript.
  3. Sends the transcript to the LLM requesting structured SOAP JSON.
  4. Parses the response (with regex code-fence stripping fallback).
  5. Persists the SOAPNote to the session_summaries table.
  6. Publishes SESSION_SUMMARIZED.

If the LLM returns malformed JSON, the summarizer logs a warning and skips
the session — note generation is best-effort, not a hard session requirement.

This is an infrastructure subscriber, NOT a BaseAgent subclass. It does not
participate in the AgentRegistry or respond to therapy events. It is
instantiated directly in main.py after registry.start_all().

@decision DEC-SUMMARY-003
@title SessionSummarizer as infrastructure subscriber (not BaseAgent)
@status accepted
@rationale SOAP note generation is a post-session infrastructure concern, not
    a therapeutic agent. It does not need name/description/supported_events
    properties, nor should it be started/stopped by AgentRegistry. The
    KnowledgeExtractor (DEC-KNOWLEDGE-003) established this pattern — plain
    class, constructor subscribes to EventBus, no registry involvement.

@decision DEC-SUMMARY-004
@title Lenient JSON extraction with regex fallback (DEC-KNOWLEDGE-004 pattern)
@status accepted
@rationale Same rationale as KnowledgeExtractor: LLMs occasionally wrap JSON
    in markdown code fences. Strip fences with regex, retry json.loads(). On
    second failure, log warning and skip — never raise into the event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from ada.core.bus import EventBus
from ada.core.events import AdaEvent, EventTypes, SessionEndedEvent, SessionSummarizedEvent
from ada.core.state import StateManager
from ada.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SOAP_SYSTEM = """\
You are a clinical documentation assistant for a mental health support platform.
Given a therapy session transcript, generate a structured SOAP note.

Respond with ONLY valid JSON — no markdown, no explanation.

The JSON must have this exact structure:
{
  "subjective": "<patient's reported experience in their own words>",
  "objective": "<observable behavioral data: tone, engagement, notable statements>",
  "assessment": "<clinical interpretation of the session>",
  "plan": "<recommended next steps, interventions, or follow-up actions>",
  "key_topics": ["<topic 1>", "<topic 2>"],
  "risk_flags": ["<concern 1>"]
}

Rules:
- subjective: quote or paraphrase what the patient expressed about their experience
- objective: note behavioral observations (not feelings — observable facts)
- assessment: synthesise what the data suggests about patient state and progress
- plan: concrete, actionable next steps (e.g., "Continue CBT thought records")
- key_topics: 1-5 main themes discussed (lowercase short phrases)
- risk_flags: only include clinically significant concerns; use empty list [] if none
"""

_SOAP_USER = """\
Session transcript:

{transcript}

Generate the SOAP note JSON.
"""

# ---------------------------------------------------------------------------
# SessionSummarizer
# ---------------------------------------------------------------------------


class SessionSummarizer:
    """
    Infrastructure subscriber that generates SOAP clinical notes at session end.

    Args:
        bus:   Running EventBus instance.
        state: Initialised StateManager.
        llm:   LLM provider used for SOAP generation.
    """

    def __init__(
        self,
        bus: EventBus,
        state: StateManager,
        llm: LLMProvider,
    ) -> None:
        self._bus = bus
        self._state = state
        self._llm = llm
        bus.subscribe(EventTypes.SESSION_ENDED, self._on_session_ended, "session_summarizer")
        logger.info("SessionSummarizer: subscribed to %s", EventTypes.SESSION_ENDED)

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    async def _on_session_ended(self, event: AdaEvent) -> None:
        """Handle a SESSION_ENDED event — generate and persist a SOAP note."""
        if not isinstance(event, SessionEndedEvent):
            return

        session_id = event.session_id
        patient_id = event.patient_id
        logger.info(
            "SessionSummarizer: processing session %s for patient %s",
            session_id,
            patient_id,
        )

        # Fetch messages
        messages = await self._state.get_messages(session_id)
        if not messages:
            logger.debug(
                "SessionSummarizer: no messages in session %s — skipping", session_id
            )
            return

        # Build transcript
        transcript = _build_transcript(messages)

        # Call LLM — bounded by a 60 s timeout (infrastructure subscriber has
        # no config reference; use the same default as LLMConfig.timeout)
        try:
            response = await asyncio.wait_for(
                self._llm.complete(
                    messages=[
                        {"role": "user", "content": _SOAP_USER.format(transcript=transcript)}
                    ],
                    system=_SOAP_SYSTEM,
                    max_tokens=1024,
                    temperature=0.2,
                ),
                timeout=60.0,
            )
        except Exception as exc:
            logger.warning(
                "SessionSummarizer: LLM call failed for session %s: %s",
                session_id,
                exc,
            )
            return

        # Parse LLM output
        parsed = _parse_soap_response(response.content)
        if parsed is None:
            logger.warning(
                "SessionSummarizer: failed to parse LLM response for session %s",
                session_id,
            )
            return

        # Build and persist summary record
        summary_id = str(uuid.uuid4())
        record: dict[str, Any] = {
            "id": summary_id,
            "session_id": session_id,
            "patient_id": patient_id,
            "subjective": str(parsed.get("subjective", "")),
            "objective": str(parsed.get("objective", "")),
            "assessment": str(parsed.get("assessment", "")),
            "plan": str(parsed.get("plan", "")),
            "key_topics": parsed.get("key_topics", []),
            "risk_flags": parsed.get("risk_flags", []),
        }

        try:
            await self._state.create_session_summary(record)
        except Exception as exc:
            logger.warning(
                "SessionSummarizer: failed to persist summary for session %s: %s",
                session_id,
                exc,
            )
            return

        # Publish SESSION_SUMMARIZED
        await self._bus.publish(
            SessionSummarizedEvent(
                source="session_summarizer",
                session_id=session_id,
                patient_id=patient_id,
                summary_id=summary_id,
            )
        )
        logger.info(
            "SessionSummarizer: SOAP note %s generated for session %s",
            summary_id,
            session_id,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_transcript(messages: list[dict[str, Any]]) -> str:
    """Format session messages into a readable transcript."""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        speaker = "Patient" if role == "user" else "Therapist"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _parse_soap_response(raw: str) -> dict[str, Any] | None:
    """
    Parse the LLM SOAP response into a dict.

    Tries direct JSON parse first, then strips markdown code fences and
    retries. Returns None if both attempts fail.
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
