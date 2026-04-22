# Patient-access authorization retrofit — design

**Date:** 2026-04-21
**Status:** approved (inline), ready to implement
**Severity:** CRITICAL security fix (IDOR on all patient-centric routes)

## Context

`/cso` audit identified that every route taking `{patient_id}` in the path only checks authentication (`Depends(get_current_user)`), not authorization. Any authenticated user can read or modify any patient's medical records, medications, cognitive assessments, treatment plans, and clinician notes. The `resolve_circle_access()` helper already exists (DEC-CIRCLE-002, `ada/api/auth.py`) and is correctly applied to boards/circles routes — it was just never retrofitted to the patient-centric routes.

## Goal

Close the IDOR by introducing a single FastAPI dependency that authorizes patient-scoped access, and applying it uniformly to every route that takes `{patient_id}`.

## Non-goals

- No change to the `resolve_circle_access` helper itself.
- No new role system (clinician, admin) beyond what exists.
- No change to request/response schemas.
- No change to the frontend — the frontend already supplies correct `patient_id`s from the selected care circle; the fix just makes the backend enforce what the UI already respects.

## Design

### 1. New dependency: `require_patient_access`

**File:** `ada/api/auth.py` (co-located with `resolve_circle_access`).

```python
async def require_patient_access(
    patient_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Authorize the caller for a specific patient_id.

    Access is granted if any of the following is true:
    1. The user's own user.patient_id matches (self-access for role=user).
    2. The user is a member of a care circle that includes this patient.
    3. The user is in the same organization (tenant mode) as the patient.

    Raises 403 (not 404) when the caller is authenticated but unauthorized —
    404 would leak patient-ID existence.
    """
```

Return `None` on success; raise `HTTPException(403)` otherwise. Keep the implementation tight — this is a hot-path check called on every patient-scoped request.

### 2. Apply to every `{patient_id}` route

**Files (apply `Depends(require_patient_access)` to each route handler):**

- `ada/api/routes/patients.py` — GET /patients/{id}, PATCH /patients/{id}
- `ada/api/routes/medications.py` — all 7 routes under /patients/{id}/medications
- `ada/api/routes/cognitive.py` — all routes under /patients/{id}/cognitive-screenings
- `ada/api/routes/daily_summaries.py` — all routes under /patients/{id}/daily-summaries
- `ada/api/routes/clinician_notes.py` — all routes under /patients/{id}/clinician-notes
- `ada/api/routes/treatment_plans.py` — all routes under /patients/{id}/treatment-plan
- `ada/api/routes/prescribing_notes.py` — all routes under /patients/{id}/prescribing-notes
- `ada/api/routes/assessments.py` — all routes under /patients/{id}/assessments
- `ada/api/routes/progress.py` or wherever progress-report / knowledge-trends routes live
- Any other router discovered during implementation that takes `{patient_id}` — grep `ada/api/routes/ -l 'patient_id'` to catch the full set.

Pattern (existing route):
```python
async def list_medications(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> list[Medication]: ...
```

Becomes:
```python
async def list_medications(
    patient_id: str,
    request: Request,
    _access: None = Depends(require_patient_access),
) -> list[Medication]: ...
```

The `_access` param name keeps the parameter unused locally but forces the dependency to run. We can drop the separate `get_current_user` dependency on these routes since `require_patient_access` depends on it transitively.

### 3. Integration test

**File:** `tests/integration/test_patient_access_authz.py` (new).

The contract:

```
For each patient-scoped endpoint (parametrize over the full list):
  register user A with patient A (via /register + circle setup)
  register user B with patient B (separate circles)
  log in as user A
  call <endpoint>.replace("{patient_id}", patient_B) with A's token
  assert response.status_code == 403
```

Also include a positive case: user A accessing patient A must still return 2xx — to catch overzealous denial.

### 4. Care-circle access

The existing `resolve_circle_access` takes `(user, circle_id, state)` and returns a membership or raises 403. The new `require_patient_access` needs to resolve `patient_id → circle_ids` first, then check if the user is in any of them. Add a helper in `state.py` if needed:

```python
async def list_circle_ids_for_patient(self, patient_id: str) -> list[str]:
    """Return all care-circle IDs that include the given patient."""
```

Then `require_patient_access` iterates: if any circle grants access, pass. Else 403.

Alternative: a single SQL query joining `care_circle_members` + `care_circles` filtered by `user_id` AND `patient_id`. Faster. Implementer's call.

## Tests

- Existing backend tests must still pass (expect some test fixtures might need a circle setup if they currently call patient routes with a loose auth token — fix the fixtures, not the dependency).
- New `test_patient_access_authz.py` must exercise at least 10 endpoints and both cross-user 403 and self-access 2xx paths.
- Frontend tests unaffected.

## Verification

1. Backend suite green: `uv run pytest tests/ -q`.
2. New authz test passes and exercises every patient-scoped endpoint on the parametrize list.
3. Live HTTP smoke (tester): register two unrelated users, cross-access returns 403 for every endpoint.
4. Existing caregiver flow still works: register caregiver, create circle with patient, access patient's progress report → 200.

## Rollout note

This is a breaking change for any existing client that was relying on the missing check. The current frontend is correct (uses circle-sourced patient_id) and will continue to work. Any external script or test that hardcoded a patient_id without circle membership will start 403-ing. That's the intended behavior.
