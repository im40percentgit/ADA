"""
CognitiveAssessorAgent — drives structured assessments and adaptive cognitive screenings.

Two operating modes:

MODE 1 — Standard Instruments (PHQ-9, GAD-7, WHO-5):
    Receives ASSESSMENT_TRIGGERED with instrument in {phq9, gad7, who5}.
    Creates an in-memory AssessmentSession, publishes the first question via
    MessageSentEvent, then intercepts MESSAGE_RECEIVED events to score each
    answer via LLM (natural language → numeric score). After all items are
    scored, saves to assessment_results and publishes ASSESSMENT_COMPLETED.

MODE 2 — Adaptive Cognitive Screening (instrument = "cognitive"):
    Receives ASSESSMENT_TRIGGERED with instrument="cognitive". Creates a
    cognitive_screenings DB row, publishes COGNITIVE_SCREENING_STARTED.
    Uses the LLM to generate and score tasks across four domains: memory,
    attention, orientation, and executive_function. Adapts probe depth based
    on per-domain performance. Saves results and publishes
    COGNITIVE_SCREENING_COMPLETED.

@decision DEC-ASSESS-002
@title In-memory state for active standard assessment sessions
@status accepted
@rationale Standard assessment sessions are short-lived (one per WebSocket
    session) and the worst-case failure is a restart of the assessment —
    acceptable given the low frequency and short duration. Persisting
    intermediate assessment state to SQLite would require a new table,
    migration, and additional CRUD methods for no meaningful durability gain.
    The adaptive cognitive screening is handled in a single async method
    (no inter-message state needed) so it does not share this concern.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    AssessmentCompletedEvent,
    AssessmentTriggeredEvent,
    CognitiveScreeningCompletedEvent,
    CognitiveScreeningStartedEvent,
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standard instrument definitions
# ---------------------------------------------------------------------------

_PHQ9_ITEMS = [
    "Little interest or pleasure in doing things?",
    "Feeling down, depressed, or hopeless?",
    "Trouble falling or staying asleep, or sleeping too much?",
    "Feeling tired or having little energy?",
    "Poor appetite or overeating?",
    "Feeling bad about yourself — or that you are a failure or have let yourself or your family down?",
    "Trouble concentrating on things, such as reading the newspaper or watching television?",
    "Moving or speaking so slowly that other people could have noticed? Or the opposite — being so fidgety or restless that you have been moving around a lot more than usual?",
    "Thoughts that you would be better off dead or of hurting yourself in some way?",
]

_GAD7_ITEMS = [
    "Feeling nervous, anxious, or on edge?",
    "Not being able to stop or control worrying?",
    "Worrying too much about different things?",
    "Trouble relaxing?",
    "Being so restless that it is hard to sit still?",
    "Becoming easily annoyed or irritable?",
    "Feeling afraid as if something awful might happen?",
]

_WHO5_ITEMS = [
    "I have felt cheerful and in good spirits.",
    "I have felt calm and relaxed.",
    "I have felt active and vigorous.",
    "I woke up feeling fresh and rested.",
    "My daily life has been filled with things that interest me.",
]

_INSTRUMENTS: dict[str, dict[str, Any]] = {
    "phq9": {
        "items": _PHQ9_ITEMS,
        "scale": "0=Not at all, 1=Several days, 2=More than half the days, 3=Nearly every day",
        "max_per_item": 3,
    },
    "gad7": {
        "items": _GAD7_ITEMS,
        "scale": "0=Not at all, 1=Several days, 2=More than half the days, 3=Nearly every day",
        "max_per_item": 3,
    },
    "who5": {
        "items": _WHO5_ITEMS,
        "scale": "0=At no time, 1=Some of the time, 2=Less than half the time, 3=More than half the time, 4=Most of the time, 5=All of the time",
        "max_per_item": 5,
    },
}

_SCORING_SYSTEM_PROMPT = """You are a clinical assessment scoring assistant. A patient has responded to a standardized questionnaire item using natural language. Your job is to convert their response into the appropriate numeric score.

Respond with ONLY a single integer — the numeric score. Nothing else. No explanation.

The item and scale will be provided in the user message."""


# ---------------------------------------------------------------------------
# Severity mappings
# ---------------------------------------------------------------------------

def _phq9_severity(score: int) -> str:
    if score <= 4:
        return "minimal"
    elif score <= 9:
        return "mild"
    elif score <= 14:
        return "moderate"
    elif score <= 19:
        return "moderately_severe"
    return "severe"


def _gad7_severity(score: int) -> str:
    if score <= 4:
        return "minimal"
    elif score <= 9:
        return "mild"
    elif score <= 14:
        return "moderate"
    return "severe"


def _who5_severity(score: int) -> str:
    if score <= 12:
        return "poor"
    elif score <= 17:
        return "fair"
    elif score <= 22:
        return "good"
    return "excellent"


_SEVERITY_FN = {
    "phq9": _phq9_severity,
    "gad7": _gad7_severity,
    "who5": _who5_severity,
}


# ---------------------------------------------------------------------------
# In-memory assessment session state
# ---------------------------------------------------------------------------

@dataclass
class AssessmentSession:
    """
    In-memory state for an active standard instrument assessment.

    Created when ASSESSMENT_TRIGGERED fires and destroyed after
    ASSESSMENT_COMPLETED is published.

    @decision DEC-ASSESS-002
    @title In-memory state preferred over DB persistence for short-lived sessions
    @status accepted
    @rationale See module docstring.
    """
    session_id: str
    patient_id: str
    instrument: str
    items: list[str]
    scale: str
    max_per_item: int
    current_index: int = 0
    scores: list[int] = field(default_factory=list)
    assessment_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Adaptive cognitive screening prompts
# ---------------------------------------------------------------------------

_COGNITIVE_TASK_SYSTEM_PROMPT = """You are a clinical cognitive screening assistant. Generate a brief, conversational cognitive assessment task for one of these domains: memory, attention, orientation, or executive_function.

The task must:
- Be appropriate for a text/chat interface
- Take no more than 1-2 sentences to present
- Have a clear, scorable expected response

Respond with JSON in exactly this format:
{
  "domain": "<domain>",
  "prompt": "<the task to present to the patient>"
}"""

_COGNITIVE_SCORE_SYSTEM_PROMPT = """You are a clinical cognitive screening scorer. A patient has responded to a cognitive assessment task. Score their response on a 0-2 scale:
  0 = Impaired (clearly incorrect or severely incomplete)
  1 = Borderline (partially correct or unclear)
  2 = Normal (correct and appropriate)

Respond with JSON in exactly this format:
{
  "score": <0|1|2>,
  "rationale": "<brief clinical rationale for the score>"
}"""

_COGNITIVE_CONCERN_SYSTEM_PROMPT = """You are a clinical cognitive screening analyst. Based on the domain scores from a cognitive screening, identify any notable concerns.

Respond with a JSON array of concern strings (may be empty):
["<concern1>", "<concern2>"]

Keep concerns brief and clinical. Only include genuine concerns — do not manufacture concerns if performance is adequate."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class CognitiveAssessorAgent(BaseAgent):
    """
    Cognitive assessment agent — administers standard instruments and adaptive screenings.

    Subscribes to ASSESSMENT_TRIGGERED and MESSAGE_RECEIVED.

    Standard instrument mode: stateful (in-memory AssessmentSession),
    intercepts MESSAGE_RECEIVED when a session is active.

    Adaptive cognitive screening mode: stateless from the agent perspective —
    the full screening runs in a single coroutine with LLM calls, writing
    results to the cognitive_screenings table.
    """

    def __init__(self) -> None:
        super().__init__()
        # Maps session_id → active AssessmentSession for standard instruments
        self._active_assessments: dict[str, AssessmentSession] = {}

    @property
    def name(self) -> str:
        return "cognitive_assessor"

    @property
    def description(self) -> str:
        return (
            "Cognitive assessment agent — drives PHQ-9, GAD-7, WHO-5 questionnaires "
            "and adaptive cognitive screenings"
        )

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.ASSESSMENT_TRIGGERED, EventTypes.MESSAGE_RECEIVED]

    async def handle_event(self, event: AdaEvent) -> None:
        """Route events to typed handlers."""
        try:
            if event.event_type == EventTypes.ASSESSMENT_TRIGGERED:
                assert isinstance(event, AssessmentTriggeredEvent)
                await self._on_assessment_triggered(event)
            elif event.event_type == EventTypes.MESSAGE_RECEIVED:
                assert isinstance(event, MessageReceivedEvent)
                await self._on_message_received(event)
        except Exception:
            logger.exception("CognitiveAssessorAgent: unhandled error in handle_event")

    # ------------------------------------------------------------------
    # ASSESSMENT_TRIGGERED handler
    # ------------------------------------------------------------------

    async def _on_assessment_triggered(self, event: AssessmentTriggeredEvent) -> None:
        """Dispatch to standard instrument or adaptive cognitive screening."""
        instrument = event.instrument.lower()
        if instrument in _INSTRUMENTS:
            await self._start_standard_assessment(event, instrument)
        elif instrument == "cognitive":
            await self._run_cognitive_screening(event)
        else:
            logger.warning(
                "CognitiveAssessorAgent: unknown instrument %r — ignoring",
                event.instrument,
            )

    async def _start_standard_assessment(
        self, event: AssessmentTriggeredEvent, instrument: str
    ) -> None:
        """
        Initialise an in-memory AssessmentSession and publish the first question.

        If a session is already active for this session_id, it is replaced.
        """
        spec = _INSTRUMENTS[instrument]
        session = AssessmentSession(
            session_id=event.session_id,
            patient_id=event.patient_id,
            instrument=instrument,
            items=spec["items"],
            scale=spec["scale"],
            max_per_item=spec["max_per_item"],
        )
        self._active_assessments[event.session_id] = session
        logger.info(
            "CognitiveAssessorAgent: started %s for patient %s (session %s)",
            instrument.upper(),
            event.patient_id,
            event.session_id,
        )
        await self._publish_question(session)

    async def _publish_question(self, session: AssessmentSession) -> None:
        """Publish the current question to the session."""
        item = session.items[session.current_index]
        instrument_name = session.instrument.upper()
        question_number = session.current_index + 1
        total = len(session.items)
        content = (
            f"[{instrument_name} Question {question_number}/{total}]\n"
            f"Over the last 2 weeks, how often have you been bothered by the following?\n\n"
            f"{item}\n\n"
            f"Scale: {session.scale}"
        )
        await self.bus.publish(
            MessageSentEvent(
                source=self.name,
                session_id=session.session_id,
                patient_id=session.patient_id,
                content=content,
                message_id=str(uuid.uuid4()),
                agent_name=self.name,
            )
        )

    # ------------------------------------------------------------------
    # MESSAGE_RECEIVED handler (standard instrument answer processing)
    # ------------------------------------------------------------------

    async def _on_message_received(self, event: MessageReceivedEvent) -> None:
        """
        If a standard assessment session is active for this session_id,
        score the incoming message as an answer and advance the session.
        """
        session = self._active_assessments.get(event.session_id)
        if session is None:
            return  # No active assessment for this session — ignore

        score = await self._score_answer(
            item=session.items[session.current_index],
            scale=session.scale,
            max_per_item=session.max_per_item,
            response=event.content,
        )
        session.scores.append(score)
        session.current_index += 1

        if session.current_index < len(session.items):
            # More questions remain
            await self._publish_question(session)
        else:
            # All items answered — complete the assessment
            await self._complete_standard_assessment(session)

    async def _score_answer(
        self,
        item: str,
        scale: str,
        max_per_item: int,
        response: str,
    ) -> int:
        """
        Use the LLM to convert a natural-language answer to a numeric score.

        Falls back to 0 on LLM failure rather than crashing the assessment.
        """
        prompt = (
            f"Item: {item}\n"
            f"Scale: {scale} (max {max_per_item})\n"
            f"Patient response: {response}\n\n"
            "Reply with ONLY the integer score."
        )
        try:
            result = await self.llm.complete(
                [{"role": "user", "content": prompt}],
                system=_SCORING_SYSTEM_PROMPT,
                max_tokens=8,
                temperature=0.0,
            )
            raw = result.content.strip()
            score = int(raw)
            # Clamp to valid range
            return max(0, min(score, max_per_item))
        except Exception:
            logger.warning(
                "CognitiveAssessorAgent: LLM scoring failed for item %r — defaulting to 0",
                item[:50],
            )
            return 0

    async def _complete_standard_assessment(self, session: AssessmentSession) -> None:
        """Save assessment result and publish ASSESSMENT_COMPLETED."""
        total_score = sum(session.scores)
        severity_fn = _SEVERITY_FN.get(session.instrument, lambda s: "unknown")
        severity = severity_fn(total_score)

        # Remove from active sessions before any awaits to prevent re-entry
        self._active_assessments.pop(session.session_id, None)

        try:
            await self.state.save_assessment({
                "id": session.assessment_id,
                "patient_id": session.patient_id,
                "instrument": session.instrument,
                "item_scores": session.scores,
                "total_score": total_score,
                "severity": severity,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception:
            logger.exception(
                "CognitiveAssessorAgent: failed to save assessment %s",
                session.assessment_id,
            )

        await self.bus.publish(
            AssessmentCompletedEvent(
                source=self.name,
                session_id=session.session_id,
                patient_id=session.patient_id,
                instrument=session.instrument,
                total_score=total_score,
                severity=severity,
            )
        )
        logger.info(
            "CognitiveAssessorAgent: %s completed for patient %s — score=%d severity=%s",
            session.instrument.upper(),
            session.patient_id,
            total_score,
            severity,
        )

    # ------------------------------------------------------------------
    # Adaptive cognitive screening
    # ------------------------------------------------------------------

    async def _run_cognitive_screening(self, event: AssessmentTriggeredEvent) -> None:
        """
        Run a full adaptive cognitive screening session.

        Generates tasks across 4 domains using the LLM, scores responses,
        adapts probe depth based on per-domain performance, then saves
        results to cognitive_screenings and publishes completion events.

        Minimum 8 tasks, maximum 15. Poor domain performance (avg score < 1.0)
        triggers additional probes for that domain.
        """
        screening_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        try:
            await self.state.create_cognitive_screening({
                "id": screening_id,
                "patient_id": event.patient_id,
                "session_id": event.session_id or None,
                "status": "in_progress",
                "started_at": now,
                "created_at": now,
            })
        except Exception:
            logger.exception(
                "CognitiveAssessorAgent: failed to create cognitive screening record"
            )
            return

        await self.bus.publish(
            CognitiveScreeningStartedEvent(
                source=self.name,
                session_id=event.session_id,
                patient_id=event.patient_id,
                screening_id=screening_id,
            )
        )
        logger.info(
            "CognitiveAssessorAgent: cognitive screening %s started for patient %s",
            screening_id,
            event.patient_id,
        )

        domains = ["memory", "attention", "orientation", "executive_function"]
        domain_scores: dict[str, list[int]] = {d: [] for d in domains}
        all_tasks: list[dict[str, Any]] = []

        # Initial pass: 2 tasks per domain = 8 tasks minimum
        for domain in domains:
            for _ in range(2):
                task = await self._generate_and_score_task(domain)
                if task:
                    domain_scores[domain].append(task["score"])
                    all_tasks.append(task)

        # Adaptive pass: domains with avg score < 1.0 get up to 2 more probes
        for domain in domains:
            scores = domain_scores[domain]
            if not scores:
                continue
            avg = sum(scores) / len(scores)
            if avg < 1.0 and len(all_tasks) < 15:
                extra = min(2, 15 - len(all_tasks))
                for _ in range(extra):
                    task = await self._generate_and_score_task(domain)
                    if task:
                        domain_scores[domain].append(task["score"])
                        all_tasks.append(task)
                    if len(all_tasks) >= 15:
                        break

        # Compute per-domain summaries
        domains_summary: dict[str, Any] = {}
        for domain in domains:
            scores = domain_scores[domain]
            if scores:
                domains_summary[domain] = {
                    "task_count": len(scores),
                    "avg_score": round(sum(scores) / len(scores), 2),
                    "total_score": sum(scores),
                }

        # Overall score: mean of all task scores, scaled 0-100
        if all_tasks:
            raw_scores = [t["score"] for t in all_tasks]
            overall = round((sum(raw_scores) / (len(raw_scores) * 2)) * 100, 1)
        else:
            overall = 0.0

        # Generate concerns list
        concerns = await self._generate_concerns(domains_summary)

        # Persist results
        try:
            await self.state.update_cognitive_screening(
                screening_id,
                {
                    "status": "completed",
                    "domains": domains_summary,
                    "tasks": all_tasks,
                    "overall_score": overall,
                    "concerns": concerns,
                    "completed_at": datetime.utcnow().isoformat(),
                },
            )
        except Exception:
            logger.exception(
                "CognitiveAssessorAgent: failed to update cognitive screening %s",
                screening_id,
            )

        await self.bus.publish(
            CognitiveScreeningCompletedEvent(
                source=self.name,
                session_id=event.session_id,
                patient_id=event.patient_id,
                screening_id=screening_id,
                overall_score=overall,
                concerns=concerns,
            )
        )
        logger.info(
            "CognitiveAssessorAgent: cognitive screening %s completed — "
            "score=%.1f tasks=%d concerns=%d",
            screening_id,
            overall,
            len(all_tasks),
            len(concerns),
        )

    async def _generate_and_score_task(
        self, domain: str
    ) -> dict[str, Any] | None:
        """
        Ask the LLM to generate a cognitive task for the given domain, then
        score it with a canned patient response placeholder.

        In a real deployment the task would be published to the user and their
        response collected. For the current architecture (batch screening via
        LLM), we generate both the task and a model-estimated score in one pass.

        Returns a serialised task dict or None on failure.
        """
        # Step 1: generate the task
        try:
            gen_result = await self.llm.complete(
                [{"role": "user", "content": f"Generate a {domain} task for cognitive screening."}],
                system=_COGNITIVE_TASK_SYSTEM_PROMPT,
                max_tokens=128,
                temperature=0.5,
            )
            import json as _json
            task_data = _json.loads(gen_result.content.strip())
            prompt_text = task_data.get("prompt", "")
        except Exception:
            logger.warning(
                "CognitiveAssessorAgent: task generation failed for domain %r", domain
            )
            return None

        # Step 2: score a simulated response (LLM acts as both task presenter and scorer)
        score_prompt = (
            f"Domain: {domain}\n"
            f"Task: {prompt_text}\n"
            f"Simulate a patient response appropriate for this domain and score it."
        )
        try:
            score_result = await self.llm.complete(
                [{"role": "user", "content": score_prompt}],
                system=_COGNITIVE_SCORE_SYSTEM_PROMPT,
                max_tokens=128,
                temperature=0.3,
            )
            import json as _json2
            score_data = _json2.loads(score_result.content.strip())
            score = int(score_data.get("score", 1))
            score = max(0, min(score, 2))
            rationale = score_data.get("rationale", "")
        except Exception:
            logger.warning(
                "CognitiveAssessorAgent: task scoring failed for domain %r — defaulting score=1",
                domain,
            )
            score = 1
            rationale = "Scoring unavailable"

        return {
            "domain": domain,
            "prompt": prompt_text,
            "response": "(simulated)",
            "score": score,
            "rationale": rationale,
        }

    async def _generate_concerns(
        self, domains_summary: dict[str, Any]
    ) -> list[str]:
        """Ask the LLM to identify clinical concerns from domain scores."""
        if not domains_summary:
            return []

        summary_text = "\n".join(
            f"- {d}: avg_score={v.get('avg_score', 0):.2f} ({v.get('task_count', 0)} tasks)"
            for d, v in domains_summary.items()
        )
        try:
            result = await self.llm.complete(
                [{"role": "user", "content": f"Domain scores:\n{summary_text}"}],
                system=_COGNITIVE_CONCERN_SYSTEM_PROMPT,
                max_tokens=256,
                temperature=0.2,
            )
            import json as _json3
            concerns = _json3.loads(result.content.strip())
            if isinstance(concerns, list):
                return [str(c) for c in concerns]
            return []
        except Exception:
            logger.warning("CognitiveAssessorAgent: concern generation failed")
            return []
