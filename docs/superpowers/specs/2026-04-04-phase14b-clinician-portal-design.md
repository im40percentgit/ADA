# Phase 14b — Clinician Portal: Treatment Planning & Prescribing

## Context

Clinicians using Ada need structured treatment planning tools beyond what the caregiver dashboard provides. Phase 14b adds goal-based treatment plans with automated progress tracking against assessment scores, plus prescribing notes that link clinical decisions to medications.

---

## 1. Treatment Plans

### Database

**`treatment_plans`**
```sql
CREATE TABLE IF NOT EXISTS treatment_plans (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    clinician_id    TEXT NOT NULL REFERENCES users(id),
    organization_id TEXT REFERENCES organizations(id),
    title           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'archived')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`treatment_goals`**
```sql
CREATE TABLE IF NOT EXISTS treatment_goals (
    id              TEXT PRIMARY KEY,
    plan_id         TEXT NOT NULL REFERENCES treatment_plans(id),
    description     TEXT NOT NULL,
    target_metric   TEXT CHECK(target_metric IN ('phq9', 'gad7', 'who5', 'cognitive', 'custom')),
    target_operator TEXT NOT NULL DEFAULT '<' CHECK(target_operator IN ('<', '>', '<=', '>=')),
    target_value    REAL,
    current_value   REAL,
    status          TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'met', 'unmet', 'deferred')),
    due_date        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`treatment_interventions`**
```sql
CREATE TABLE IF NOT EXISTS treatment_interventions (
    id              TEXT PRIMARY KEY,
    goal_id         TEXT NOT NULL REFERENCES treatment_goals(id),
    description     TEXT NOT NULL,
    frequency       TEXT,
    status          TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'discontinued')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Auto-Progress Tracking

When assessment scores are saved (existing `AssessmentCompletedEvent`), check treatment goals:
- Find active goals with matching `target_metric` for the patient
- Update `current_value` with the new assessment score
- If `current_value` meets target (operator + value): set `status = 'met'`
- Publish `TreatmentGoalMetEvent` for notification

### API Endpoints

- `POST /api/patients/{id}/treatment-plans` — create plan (clinician only)
- `GET /api/patients/{id}/treatment-plans` — list plans
- `GET /api/treatment-plans/{id}` — plan detail with goals and interventions
- `PUT /api/treatment-plans/{id}` — update plan status/title
- `POST /api/treatment-plans/{id}/goals` — add goal
- `PUT /api/treatment-goals/{id}` — update goal
- `POST /api/treatment-goals/{id}/interventions` — add intervention
- `PUT /api/treatment-interventions/{id}` — update intervention

---

## 2. Prescribing Notes

### Database

**`prescribing_notes`**
```sql
CREATE TABLE IF NOT EXISTS prescribing_notes (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    clinician_id    TEXT NOT NULL REFERENCES users(id),
    medication_id   TEXT REFERENCES medications(id),
    note_type       TEXT NOT NULL CHECK(note_type IN ('prescribe', 'adjust', 'discontinue', 'review')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### API Endpoints

- `POST /api/patients/{id}/prescribing-notes` — create note (clinician only)
- `GET /api/patients/{id}/prescribing-notes` — list notes (newest first)

---

## 3. Treatment Plan UI

### TreatmentPlan.tsx

Accessed from clinician's view of a patient (via dashboard or patient detail).

Layout:
- Plan header: title (editable), status Badge (active/completed/archived)
- Goals list: each goal as a Card with:
  - Description
  - Target: "{metric} {operator} {value}" (e.g., "PHQ-9 < 10")
  - Current value with progress bar toward target
  - Status Badge (active/met/unmet)
  - Due date if set
  - Interventions list (expandable): each with description, frequency, status
- Add Goal form: description input, metric picker, operator, target value, due date
- Add Intervention form (within a goal): description, frequency

### Auto-progress display
When `current_value` is available: show progress bar (current / target), color-coded (green if met, amber if close, red if far).

---

## 4. Prescribing Notes UI

### PrescribingNotes.tsx

Timeline of prescribing decisions for a patient.

- Chronological list (newest first)
- Each note: type Badge (prescribe=green, adjust=amber, discontinue=red, review=blue), linked medication name (if any), content text, clinician name, date
- Add note form: type picker, medication selector (from patient's medications), content textarea

---

## 5. Navigation Integration

- Clinician dashboard: "Treatment Plans" section showing active plans per patient
- Patient detail (clinician view): "Treatment Plan" and "Prescribing Notes" tabs
- Extend App.tsx View type + routing

---

## Files Summary

### New Files
- `ada/api/routes/treatment_plans.py`
- `ada/api/routes/prescribing_notes.py`
- `tests/unit/test_treatment_plans.py`
- `tests/unit/test_prescribing_notes.py`
- `web/src/components/TreatmentPlan.tsx`
- `web/src/components/PrescribingNotes.tsx`
- `web/test/components/TreatmentPlan.test.tsx`
- `web/test/components/PrescribingNotes.test.tsx`

### Modified Files
- `ada/core/state.py` — 3 new tables + CRUD
- `ada/core/events.py` — TreatmentGoalMetEvent
- `ada/agents/cognitive_assessor.py` — trigger goal progress check on assessment complete
- `ada/api/app.py` — register routers
- `web/src/types/index.ts` — TreatmentPlan, Goal, Intervention, PrescribingNote types
- `web/src/api/client.ts` — treatment plan + prescribing API functions
- `web/src/App.tsx` — treatment plan + prescribing views
- `web/src/components/CaregiverDashboard.tsx` — treatment plan section for clinicians
- `web/test/msw/handlers.ts` + `web/test/factories.ts`
