"""
Assessment history tracker — persists and retrieves scored results.

Bridges the assessment instruments (pure scoring) and the StateManager
(persistence). Agents call the tracker rather than the state manager
directly to keep persistence logic centralised.

@decision DEC-CORE-002
@title SQLite via aiosqlite for state
@status accepted
@rationale Assessment history is stored in SQLite via StateManager. The tracker
    provides a domain-focused facade so agents don't need to know about raw SQL
    or JSON serialisation of item_scores.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from ada.assessment.instruments import InstrumentName, ScoringResult, score_instrument
from ada.core.state import StateManager

logger = logging.getLogger(__name__)


class AssessmentTracker:
    """
    Persists assessment results and retrieves history for a patient.

    Args:
        state: Initialised StateManager instance.
    """

    def __init__(self, state: StateManager) -> None:
        self._state = state

    async def score_and_save(
        self,
        patient_id: str,
        instrument: InstrumentName,
        item_scores: list[int],
    ) -> ScoringResult:
        """
        Score an instrument and persist the result.

        Args:
            patient_id: The patient this result belongs to.
            instrument: "phq9", "gad7", or "who5".
            item_scores: Raw item responses.

        Returns:
            The ScoringResult (also persisted to SQLite).
        """
        result = score_instrument(instrument, item_scores)
        record = {
            "id": str(uuid.uuid4()),
            "patient_id": patient_id,
            "instrument": instrument,
            "item_scores": result.item_scores,
            "total_score": result.total_score,
            "severity": result.severity,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._state.save_assessment(record)
        logger.info(
            "AssessmentTracker: saved %s for patient %s (score=%d severity=%s)",
            instrument,
            patient_id,
            result.total_score,
            result.severity,
        )
        return result

    async def get_history(
        self,
        patient_id: str,
        instrument: InstrumentName | None = None,
    ) -> list[dict]:
        """
        Retrieve assessment history for a patient.

        Args:
            patient_id: Patient identifier.
            instrument: Optional filter — if None, returns all instruments.

        Returns:
            List of assessment records, newest first.
        """
        return await self._state.get_assessments(patient_id, instrument)

    async def latest(
        self,
        patient_id: str,
        instrument: InstrumentName,
    ) -> dict | None:
        """
        Return the most recent result for a given instrument, or None.

        Args:
            patient_id: Patient identifier.
            instrument: The instrument to look up.

        Returns:
            Assessment record dict or None if no results exist.
        """
        history = await self._state.get_assessments(patient_id, instrument)
        return history[0] if history else None
