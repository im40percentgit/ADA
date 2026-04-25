"""
Daily verdict generator — Phase 15+ M3 (shadow mode).

Main entry point: generate_verdict_for_date().

Architecture:
  1. Check idempotency — if a verdict already exists for patient/date, return it.
  2. Compute CLP features via clp_features.compute_today_features().
  3. Short-circuit to NO_SIGNAL if both today and yesterday are empty.
  4. Compute baseline via clp_features.compute_baseline().
  5. Build prompt via prompt.build_prompt().
  6. Call LLM with 3-attempt exponential backoff (1s → 4s → 16s).
  7. Parse JSON response; apply bias-toward-UNSURE post-processing.
  8. Persist via StateManager.upsert_daily_verdict(); return DailyVerdict.

Failure handling (DEC-VERDICT-003):
  On total LLM failure (3 retries exhausted), a synthetic UNSURE verdict is
  persisted so the founder is never left with a silent miss. The explanation
  text explicitly says "check in" so the caregiver knows to act proactively.

@decision DEC-VERDICT-003
@title Retry 3x with exponential backoff (1s/4s/16s) + synthetic UNSURE fallback
@status accepted
@rationale Caregiver never gets a silent miss. A failed verdict still produces
    a row in daily_verdicts with explanation "Verdict generator failed — please
    check in." so the labeling flow and calibration metrics see every day.
    Exponential backoff (1/4/16s) reduces thundering-herd pressure on the LLM
    API if the outage is transient.

@decision DEC-VERDICT-004
@title Bias-toward-UNSURE post-processing after LLM parse
@status accepted
@rationale At N=1, false OK before a fall or false OFF causing a panic-drive
    both permanently burn trust. Two explicit downgrade rules:
      1. Explanation too short (< 10 chars) — LLM didn't actually explain,
         downgrade to UNSURE.
      2. OFF verdict with dimension=None or 'none' — no specific dimension
         cited means the model expressed negative valence without a legible
         signal; downgrade to UNSURE because the caregiver can't act on it.

@decision DEC-VERDICT-005
@title Manual API trigger only in scaffold; nightly cron deferred
@status accepted
@rationale Dogfooding loop is tighter when the founder runs generation on
    demand during early calibration. Cron is a follow-up; this module is
    stateless and idempotent so adding a scheduler later requires zero changes
    to the generator logic. Documented in CHOICE.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from typing import Any

from ada.verdict.clp_features import compute_baseline, compute_today_features
from ada.verdict.models import (
    VERDICT_NO_SIGNAL,
    VERDICT_OFF,
    VERDICT_UNSURE,
    DailyVerdict,
)
from ada.verdict.prompt import PROMPT_VERSION, build_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry policy constants (DEC-VERDICT-003)
# ---------------------------------------------------------------------------
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = [1.0, 4.0, 16.0]  # attempt 0, 1, 2

# ---------------------------------------------------------------------------
# Synthetic fallback constants
# ---------------------------------------------------------------------------
_SYNTHETIC_MODEL = "none"
_SYNTHETIC_EXPLANATION = "Verdict generator failed — please check in."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_bias_toward_unsure(
    verdict: str,
    explanation: str,
    dimension: str | None,
) -> tuple[str, str, str | None]:
    """
    Post-process LLM output with bias-toward-UNSURE rules.

    Rules (DEC-VERDICT-004):
      1. Explanation too short → downgrade to UNSURE.
      2. OFF with no legible dimension → downgrade to UNSURE.

    Returns:
        (verdict, explanation, dimension) — possibly modified.
    """
    # bias-toward-UNSURE rule 1: explanation below minimum length
    if len(explanation.strip()) < 10:  # bias-toward-UNSURE
        logger.debug("bias-toward-UNSURE: explanation too short (%d chars)", len(explanation))
        return VERDICT_UNSURE, "Signal present but explanation too thin to act on.", dimension

    # bias-toward-UNSURE rule 2: OFF without a legible dimension
    if verdict == VERDICT_OFF and (not dimension or dimension.lower() in ("none", "null", "")):  # bias-toward-UNSURE
        logger.debug("bias-toward-UNSURE: OFF with no dimension — downgrading to UNSURE")
        return VERDICT_UNSURE, explanation, dimension

    return verdict, explanation, dimension


def _parse_llm_response(content: str) -> tuple[str, str, str | None]:
    """
    Parse the LLM JSON response into (verdict, explanation, dimension).

    Raises:
        ValueError: If the content is not valid JSON or missing required keys.
    """
    # Strip markdown code fences if present
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop first and last fence lines
        stripped = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM response is not a JSON object: {content!r}")

    verdict = str(parsed.get("verdict", "")).strip().upper()
    explanation = str(parsed.get("explanation", "")).strip()
    dimension_raw = parsed.get("dimension")
    dimension: str | None = str(dimension_raw).strip() if dimension_raw not in (None, "null", "none", "None") else None

    if not verdict:
        raise ValueError(f"LLM response missing 'verdict' key: {content!r}")
    if not explanation:
        raise ValueError(f"LLM response missing 'explanation' key: {content!r}")

    return verdict, explanation, dimension


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_verdict_for_date(
    state_manager: Any,
    llm_provider: Any,
    patient_id: str,
    verdict_date: date,
) -> DailyVerdict:
    """
    Generate (or retrieve) the daily verdict for a patient on a given date.

    Idempotent: if a verdict already exists for patient_id + verdict_date,
    returns the existing row without calling the LLM.

    Args:
        state_manager: Initialised StateManager instance.
        llm_provider: LLMProvider instance (e.g. ClaudeProvider). Used only
            when a new verdict needs to be generated — not called on cache hit
            or NO_SIGNAL short-circuit.
        patient_id: Patient identifier.
        verdict_date: The date to generate a verdict for.

    Returns:
        DailyVerdict — either freshly generated or loaded from the DB.
    """
    date_str = verdict_date.isoformat()

    # --- Idempotency check ---
    existing = await state_manager.get_daily_verdict(patient_id, date_str)
    if existing:
        logger.debug("generate_verdict_for_date: cache hit for %s / %s", patient_id, date_str)
        return DailyVerdict.from_db_dict(existing)

    # --- Feature extraction ---
    today_features = await compute_today_features(state_manager, patient_id, verdict_date)

    # --- NO_SIGNAL short-circuit (no LLM call) ---
    if today_features.get("no_signal"):
        logger.info("generate_verdict_for_date: NO_SIGNAL for %s on %s", patient_id, date_str)
        verdict = DailyVerdict(
            patient_id=patient_id,
            verdict_date=date_str,
            verdict=VERDICT_NO_SIGNAL,
            explanation="No solitaire sessions today or yesterday.",
            dimension=None,
            model_used=_SYNTHETIC_MODEL,
            prompt_version=PROMPT_VERSION,
            telemetry_summary={"no_signal": True},
            baseline_summary="insufficient",
            generated_at=datetime.utcnow().isoformat(),
        )
        row_id = await state_manager.upsert_daily_verdict(verdict.to_db_dict())
        verdict.id = row_id
        return verdict

    # --- Baseline computation ---
    baseline = await compute_baseline(state_manager, patient_id, verdict_date)

    # --- Build prompt ---
    prompt_text = build_prompt(today_features, baseline)

    # --- LLM call with exponential backoff retry (DEC-VERDICT-003) ---
    model_used = "unknown"
    verdict_str = VERDICT_UNSURE
    explanation = _SYNTHETIC_EXPLANATION
    dimension: str | None = None
    llm_succeeded = False

    for attempt in range(_MAX_ATTEMPTS):
        if attempt > 0:
            delay = _BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                "generate_verdict_for_date: LLM attempt %d/%d failed, retrying in %.0fs",
                attempt, _MAX_ATTEMPTS, delay,
            )
            await asyncio.sleep(delay)

        try:
            response = await llm_provider.complete(
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=256,
                temperature=0.2,  # Low temperature for consistent structured output
            )
            model_used = response.model
            raw_verdict, raw_explanation, raw_dimension = _parse_llm_response(response.content)

            # Apply bias-toward-UNSURE post-processing (DEC-VERDICT-004)
            verdict_str, explanation, dimension = _apply_bias_toward_unsure(
                raw_verdict, raw_explanation, raw_dimension
            )
            llm_succeeded = True
            break

        except Exception as exc:
            logger.warning(
                "generate_verdict_for_date: attempt %d/%d error: %s",
                attempt + 1, _MAX_ATTEMPTS, exc,
            )

    if not llm_succeeded:
        logger.error(
            "generate_verdict_for_date: all %d attempts failed for %s / %s — "
            "persisting synthetic UNSURE (DEC-VERDICT-003)",
            _MAX_ATTEMPTS, patient_id, date_str,
        )
        verdict_str = VERDICT_UNSURE
        explanation = _SYNTHETIC_EXPLANATION
        model_used = _SYNTHETIC_MODEL
        dimension = None

    # --- Persist ---
    dv = DailyVerdict(
        patient_id=patient_id,
        verdict_date=date_str,
        verdict=verdict_str,
        explanation=explanation,
        dimension=dimension,
        model_used=model_used,
        prompt_version=PROMPT_VERSION,
        telemetry_summary=today_features,
        baseline_summary=baseline,
        generated_at=datetime.utcnow().isoformat(),
    )
    row_id = await state_manager.upsert_daily_verdict(dv.to_db_dict())
    dv.id = row_id
    logger.info(
        "generate_verdict_for_date: persisted verdict=%s id=%d for %s / %s (llm_ok=%s)",
        dv.verdict, row_id, patient_id, date_str, llm_succeeded,
    )
    return dv
