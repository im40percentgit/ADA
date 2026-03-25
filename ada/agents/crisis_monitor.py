"""
CrisisMonitorAgent — two-stage crisis detection pipeline.

Stage 1: Fast keyword/pattern scan over incoming message content.
Stage 2: LLM analysis for nuanced cases that keyword scan flags as uncertain.

Always errs toward higher severity. CRITICAL events trigger immediate
crisis resource messaging. All alerts are persisted to SQLite regardless
of severity.

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale A pure keyword scan has high false-positive rate but catches
    obvious cases instantly. LLM analysis handles nuanced phrasing
    ("I want to go to sleep and never wake up") that keywords miss.
    The two stages together give safety with reduced alert fatigue.

@decision DEC-AGENT-002
@title Safety-first — always err toward higher severity
@status accepted
@rationale In a mental health context, a missed CRITICAL event is
    catastrophic. A false positive causes mild disruption. The LLM
    analysis prompt instructs the model to prefer higher severity when
    uncertain. CRITICAL always triggers crisis resources regardless of
    detection method.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    CrisisDetectedEvent,
    EventTypes,
    MessageReceivedEvent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword tiers — ordered from highest to lowest severity
# ---------------------------------------------------------------------------

_CRITICAL_PATTERNS = [
    r"\bsuicid\w*\b",
    r"\bkill\s+myself\b",
    r"\bend\s+my\s+life\b",
    r"\bend\s+it\s+all\b",
    r"\bwant\s+to\s+die\b",
    r"\bbetter\s+off\s+dead\b",
    r"\boverdos\w*\b",
    r"\bself.?harm\b",
    r"\bcut\s+(my|myself)\b",
    r"\bhang\s+(my)?self\b",
    r"\bjump\s+(off|from)\b",
]

_HIGH_PATTERNS = [
    r"\bhopeless\b",
    r"\bno\s+reason\s+to\s+live\b",
    r"\bcan'?t\s+go\s+on\b",
    r"\bgive\s+up\b",
    r"\bworthless\b",
    r"\bnobody\s+cares\b",
    r"\bdon'?t\s+want\s+to\s+be\s+here\b",
]

_MODERATE_PATTERNS = [
    r"\bhurt\s+myself\b",
    r"\bself\s+destruct\w*\b",
    r"\bpunish\s+myself\b",
    r"\bdesperats?\b",
    r"\btrapped\b",
    r"\bno\s+way\s+out\b",
]

_LOW_PATTERNS = [
    r"\bnumb\b",
    r"\bempty\b",
    r"\balone\b",
    r"\bdark\s+(thoughts?|place)\b",
]

_COMPILED: dict[str, list[re.Pattern]] = {
    "CRITICAL": [re.compile(p, re.IGNORECASE) for p in _CRITICAL_PATTERNS],
    "HIGH": [re.compile(p, re.IGNORECASE) for p in _HIGH_PATTERNS],
    "MODERATE": [re.compile(p, re.IGNORECASE) for p in _MODERATE_PATTERNS],
    "LOW": [re.compile(p, re.IGNORECASE) for p in _LOW_PATTERNS],
}

_SEVERITY_ORDER = ["CRITICAL", "HIGH", "MODERATE", "LOW"]

_CRISIS_RESOURCES = (
    "If you are in immediate danger, please call emergency services (911) or "
    "a crisis line such as the 988 Suicide & Crisis Lifeline (call or text 988 in the US). "
    "You are not alone, and help is available right now."
)

_LLM_ANALYSIS_PROMPT = """You are a mental health crisis assessment assistant.
Assess the following message for signs of suicidal ideation, self-harm, or acute mental health crisis.

Message: {message}

Respond with a JSON object with exactly these fields:
{{
  "severity": "CRITICAL" | "HIGH" | "MODERATE" | "LOW" | "NONE",
  "reasoning": "brief explanation",
  "confidence": "high" | "medium" | "low"
}}

When uncertain, prefer a HIGHER severity rating. A missed crisis is far worse than a false alarm.
Respond ONLY with the JSON object, no other text."""


class CrisisMonitorAgent(BaseAgent):
    """
    Two-stage crisis detection agent.

    Stage 1 (keyword scan) runs synchronously on every message.
    Stage 2 (LLM analysis) runs when Stage 1 returns LOW or when the
    message has emotional language that warrants deeper analysis.
    """

    @property
    def name(self) -> str:
        return "crisis_monitor"

    @property
    def description(self) -> str:
        return "Two-stage crisis detection: keyword scan + LLM analysis"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.MESSAGE_RECEIVED]

    async def handle_event(self, event: AdaEvent) -> None:
        """Process incoming messages for crisis indicators."""
        if not isinstance(event, MessageReceivedEvent):
            return
        try:
            await self._analyse(event)
        except Exception:
            logger.exception("CrisisMonitorAgent: unhandled error in handle_event")

    # ------------------------------------------------------------------
    # Detection pipeline
    # ------------------------------------------------------------------

    async def _analyse(self, event: MessageReceivedEvent) -> None:
        content = event.content
        session_id = event.session_id
        patient_id = event.patient_id

        # Stage 1: keyword scan
        keyword_severity, matched_pattern = _keyword_scan(content)

        if keyword_severity in ("CRITICAL", "HIGH"):
            # High confidence — act immediately
            await self._raise_alert(
                session_id=session_id,
                patient_id=patient_id,
                severity=keyword_severity,
                trigger_text=content[:500],
                detection_method="keyword",
                escalation_action=_escalation_action(keyword_severity),
            )
            return

        if keyword_severity in ("MODERATE", "LOW") or _has_emotional_language(content):
            # Stage 2: LLM analysis for nuanced assessment
            llm_severity = await self._llm_analyse(content)
            if llm_severity and llm_severity != "NONE":
                # Use the higher of keyword and LLM severity
                final_severity = _higher_severity(keyword_severity or "NONE", llm_severity)
                await self._raise_alert(
                    session_id=session_id,
                    patient_id=patient_id,
                    severity=final_severity,
                    trigger_text=content[:500],
                    detection_method="llm",
                    escalation_action=_escalation_action(final_severity),
                )

    async def _llm_analyse(self, content: str) -> str | None:
        """Run LLM-based crisis analysis. Returns severity string or None on error."""
        import json

        prompt = _LLM_ANALYSIS_PROMPT.format(message=content[:1000])
        try:
            response = await asyncio.wait_for(
                self.llm.complete(
                    [{"role": "user", "content": prompt}],
                    max_tokens=200,
                    temperature=0.1,   # Low temperature for consistent JSON output
                ),
                timeout=self.config.llm.timeout,
            )
            # Parse JSON response
            raw = response.content.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            return data.get("severity", "NONE")
        except Exception:
            logger.exception("CrisisMonitorAgent: LLM analysis failed")
            return None

    async def _raise_alert(
        self,
        *,
        session_id: str,
        patient_id: str,
        severity: str,
        trigger_text: str,
        detection_method: str,
        escalation_action: str,
    ) -> None:
        """Persist and publish a crisis alert."""
        alert_id = str(uuid.uuid4())

        # Always persist — Safety Practice
        await self.state.save_crisis_alert({
            "id": alert_id,
            "patient_id": patient_id,
            "session_id": session_id,
            "severity": severity,
            "trigger_text": trigger_text,
            "detection_method": detection_method,
            "escalation_action": escalation_action,
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.warning(
            "CrisisMonitorAgent: %s alert [%s] patient=%s method=%s",
            severity,
            alert_id,
            patient_id,
            detection_method,
        )

        await self.bus.publish(
            CrisisDetectedEvent(
                source=self.name,
                session_id=session_id,
                patient_id=patient_id,
                severity=severity,
                trigger_text=trigger_text,
                detection_method=detection_method,
                escalation_action=escalation_action,
            )
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _keyword_scan(text: str) -> tuple[str | None, str | None]:
    """
    Scan text for crisis keywords in severity order.

    Returns:
        (severity, matched_pattern_string) or (None, None) if no match.
    """
    for severity in _SEVERITY_ORDER:
        for pattern in _COMPILED[severity]:
            m = pattern.search(text)
            if m:
                return severity, m.group(0)
    return None, None


def _has_emotional_language(text: str) -> bool:
    """Heuristic: does the text have sufficient emotional content to warrant LLM analysis?"""
    emotional_words = {
        "feel", "feeling", "felt", "emotion", "hurt", "pain", "suffer",
        "struggle", "hard", "difficult", "cannot", "can't", "anymore",
    }
    words = set(text.lower().split())
    return bool(words & emotional_words)


def _higher_severity(a: str, b: str) -> str:
    """Return the higher of two severity strings."""
    order = {s: i for i, s in enumerate(_SEVERITY_ORDER)}
    # Lower index = higher severity in _SEVERITY_ORDER
    a_idx = order.get(a, len(_SEVERITY_ORDER))
    b_idx = order.get(b, len(_SEVERITY_ORDER))
    return a if a_idx <= b_idx else b


def _escalation_action(severity: str) -> str:
    """Return the escalation action string for a given severity."""
    actions = {
        "CRITICAL": f"Immediate crisis response required. {_CRISIS_RESOURCES}",
        "HIGH": "High-risk content detected. Review recommended.",
        "MODERATE": "Moderate risk content flagged for review.",
        "LOW": "Low-risk content noted.",
    }
    return actions.get(severity, "")
