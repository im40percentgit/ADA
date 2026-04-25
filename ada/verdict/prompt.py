"""
Versioned verdict prompt module — Phase 15+ M3.

Contains the verbatim first-cut prompt from the design doc's
"Verdict prompt — first cut (M0 spike #2 deliverable)" section.
Exposes build_prompt() to fill telemetry and baseline placeholders.

@decision DEC-VERDICT-002
@title JSON-shaped LLM output with explicit dimension field
@status accepted
@rationale Machine-parseable output with keys (verdict, explanation,
    dimension) allows programmatic post-processing without brittle string
    parsing. The dimension field is separately tagged so the bias-toward-UNSURE
    rule (DEC-VERDICT-004) can inspect it independently of the explanation text.

Prompt iteration: this is v1 — the seed frame from the founder's Digital
Phenotyping analysis. It will be iterated against hand-labeled retro days
during M0 spike #2 execution. Each new version gets its own PROMPT_VERSION
constant and the generator passes it through to the DB row so we can track
which prompt produced which verdict.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Prompt version tag — stored in every daily_verdicts row so we can
# attribute accuracy improvements to specific prompt iterations.
# ---------------------------------------------------------------------------
PROMPT_VERSION = "v1"

# ---------------------------------------------------------------------------
# Verbatim first-cut prompt from design doc §"Verdict prompt — first cut"
# Placeholders: {telemetry_summary} and {baseline_summary}
# ---------------------------------------------------------------------------
_PROMPT_TEMPLATE = """\
Given today's solitaire session(s) for {patient_name}, compared to their
21-day rolling baseline, output exactly one of: OK / OFF / UNSURE / NO_SIGNAL,
plus a one-sentence explanation citing the dimension that shifted.

Dimensions to consider (Cognitive Load Profile):
- Anxiety/hyperarousal: faster decision time + higher error rate vs baseline
- Depression/lethargy: longer move latency + shorter session vs baseline
- Cognitive disorganization: undo spikes + invalid-click spikes vs baseline
- Mania/hyperfocus: faster + longer + lower error vs baseline (rare; flag)
- Frustration/regulation: restart count departure from baseline (in either direction)
- Dissociation: invalid-move sequences without recovery

Output UNSURE if dimensions conflict (e.g., anxiety + lethargy both lit).
Output NO_SIGNAL if zero sessions today AND zero sessions yesterday.
BIAS TOWARD UNSURE — wrong verdicts permanently burn trust at N=1.

Today's signal:
{telemetry_summary}

21-day baseline (or "insufficient" if < 14 baseline days):
{baseline_summary}

Output JSON: {{ "verdict": "OK|OFF|UNSURE|NO_SIGNAL", "explanation": "<one sentence>", "dimension": "<dimension or 'none'>" }}\
"""


def build_prompt(
    telemetry_summary: dict,
    baseline_summary: dict | str,
    *,
    patient_name: str = "the patient",
) -> str:
    """
    Build the verdict prompt by filling placeholders.

    Args:
        telemetry_summary: CLP features dict from clp_features.compute_today_features().
        baseline_summary: Baseline dict from clp_features.compute_baseline(), or the
            literal string "insufficient" when fewer than min_days are available.
        patient_name: Display name for the patient — included in the prompt for
            clarity. Defaults to "the patient" to avoid PII leakage in logs.

    Returns:
        Fully formatted prompt string ready for LLM submission.
    """
    if isinstance(baseline_summary, str):
        baseline_str = baseline_summary
    else:
        baseline_str = json.dumps(baseline_summary, indent=2)

    return _PROMPT_TEMPLATE.format(
        patient_name=patient_name,
        telemetry_summary=json.dumps(telemetry_summary, indent=2),
        baseline_summary=baseline_str,
    )
