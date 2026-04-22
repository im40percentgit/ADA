# Treatment-plan sub-resource authz — design

**Date:** 2026-04-21
**Status:** approved (inline), ready to implement
**Severity:** HIGH security follow-up to the patient-access IDOR fix merged earlier today

## Context

The earlier patch gated every route with `{patient_id}` in the path. Tester's follow-up review surfaced a secondary IDOR in `ada/api/routes/treatment_plans.py` — six routes use `{plan_id}`, `{goal_id}`, or `{intervention_id}` in the path (not `{patient_id}`) and were not covered by that fix. An attacker who obtains a treatment plan / goal / intervention UUID (via enumeration, leak, prior access, or shared-circle read-through) can read or mutate it regardless of whether they have access to the underlying patient.

Affected routes (all in `ada/api/routes/treatment_plans.py`):

- `GET /api/treatment-plans/{plan_id}`
- `PUT /api/treatment-plans/{plan_id}` (also requires clinician role)
- `POST /api/treatment-plans/{plan_id}/goals` (also requires clinician role)
- `PUT /api/treatment-goals/{goal_id}` (also requires clinician role)
- `POST /api/treatment-goals/{goal_id}/interventions` (also requires clinician role)
- `PUT /api/treatment-interventions/{intervention_id}` (also requires clinician role)

The existing clinician-role check is orthogonal — it stops a non-clinician from mutating, but does NOT stop a clinician in circle A from mutating a plan belonging to circle B.

## Goal

Extend the patient-access authorization to these sub-resource routes by resolving the sub-resource ID up to its owning patient, then reusing the patient-access logic shipped earlier today.

## Non-goals

- No new role system.
- No change to response schemas.
- No deprecation of existing routes.
- No change to the `require_patient_access` dependency itself — we share its core.

## Design

### 1. Refactor `require_patient_access` to expose its core

In `ada/api/auth.py`, factor out the actual access decision so multiple dependencies can call it with a resolved `patient_id`:

```python
async def _enforce_patient_access(
    patient_id: str,
    user: User,
    state: StateManager,
) -> None:
    """Shared authz core — raises 403 if user can't access patient_id."""
    if user.patient_id == patient_id:
        return
    if await state.user_can_access_patient(user.id, patient_id):
        return
    raise HTTPException(403, "Forbidden")


async def require_patient_access(patient_id: str, request: Request, user: User = Depends(get_current_user)) -> None:
    await _enforce_patient_access(patient_id, user, _state(request))
```

### 2. Add three new dependencies

```python
async def require_plan_access(
    plan_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    state = _state(request)
    patient_id = await state.get_patient_id_for_plan(plan_id)
    if patient_id is None:
        raise HTTPException(404, "Treatment plan not found")
    await _enforce_patient_access(patient_id, user, state)


async def require_goal_access(goal_id: str, request: Request, user: User = Depends(get_current_user)) -> None:
    state = _state(request)
    patient_id = await state.get_patient_id_for_goal(goal_id)
    if patient_id is None:
        raise HTTPException(404, "Treatment goal not found")
    await _enforce_patient_access(patient_id, user, state)


async def require_intervention_access(intervention_id: str, request: Request, user: User = Depends(get_current_user)) -> None:
    state = _state(request)
    patient_id = await state.get_patient_id_for_intervention(intervention_id)
    if patient_id is None:
        raise HTTPException(404, "Treatment intervention not found")
    await _enforce_patient_access(patient_id, user, state)
```

### 3. Add three lookup helpers to `StateManager`

In `ada/core/state.py`:

```python
async def get_patient_id_for_plan(self, plan_id: str) -> str | None:
    row = await self._fetch_one("SELECT patient_id FROM treatment_plans WHERE id = :id", {"id": plan_id})
    return row["patient_id"] if row else None

async def get_patient_id_for_goal(self, goal_id: str) -> str | None:
    row = await self._fetch_one(
        "SELECT p.patient_id FROM treatment_plans p JOIN treatment_goals g ON g.plan_id = p.id WHERE g.id = :id",
        {"id": goal_id},
    )
    return row["patient_id"] if row else None

async def get_patient_id_for_intervention(self, intervention_id: str) -> str | None:
    row = await self._fetch_one(
        """SELECT p.patient_id FROM treatment_plans p
           JOIN treatment_goals g ON g.plan_id = p.id
           JOIN treatment_interventions i ON i.goal_id = g.id
           WHERE i.id = :id""",
        {"id": intervention_id},
    )
    return row["patient_id"] if row else None
```

Use the existing `_fetch_one` (or whatever single-row helper exists) — match the style used by other state helpers.

### 4. Apply deps to the six routes

In `ada/api/routes/treatment_plans.py`, add `Depends(require_plan_access)` / `require_goal_access` / `require_intervention_access` to each route:

| Route | Dependency |
|---|---|
| `GET /treatment-plans/{plan_id}` | `require_plan_access` |
| `PUT /treatment-plans/{plan_id}` | `require_plan_access` (+ existing clinician check) |
| `POST /treatment-plans/{plan_id}/goals` | `require_plan_access` |
| `PUT /treatment-goals/{goal_id}` | `require_goal_access` |
| `POST /treatment-goals/{goal_id}/interventions` | `require_goal_access` |
| `PUT /treatment-interventions/{intervention_id}` | `require_intervention_access` |

The existing `_require_clinician_or_admin(user)` calls stay — that's a separate role gate.

Since `require_*_access` does the existence check (returns 404 if the plan/goal/intervention doesn't exist), the handlers can drop their duplicate "existing is None" checks. Leave them if removing them risks a behavior change — safe to leave as belt-and-braces.

### 5. Test contract

New file `tests/integration/test_treatment_plan_authz.py` or extend the existing `test_patient_access_authz.py`:

- Register user A with patient A + treatment plan + goal + intervention owned by A.
- Register user B with patient B (separate circle, no overlap).
- Log in as B.
- For each of the six routes, call with B's token against A's plan/goal/intervention IDs. Assert 403.
- For each, call with A's token against A's own IDs. Assert 2xx.
- Cross-circle caregiver case: a caregiver in A's circle can access → 2xx.

## Tests

1. Full backend suite stays green.
2. New (or extended) authz test exercises all six routes with 403 + 2xx cases.
3. Existing `test_treatment_plans.py` unit tests must continue to pass — their fixtures likely need a circle setup so the authorized user has legitimate access.

## Verification

1. `uv run pytest tests/ -q --ignore=tests/integration/test_ml_pipeline.py --ignore=tests/unit/test_audio_features.py --ignore=tests/unit/test_face_features.py --ignore=tests/unit/test_facial_emotion_agent.py --ignore=tests/unit/test_voice_emotion_agent.py`
2. Cross-user 403 + self 200 HTTP probe against a worktree server (the tester did this for the prior fix; same pattern here).
