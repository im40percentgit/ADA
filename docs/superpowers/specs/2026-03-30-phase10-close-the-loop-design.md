# Phase 10 — Close the Product Loop

## Problem

Ada has 16 agents, 14 API route files, and 914 tests — but the user-facing product doesn't close the loop. A caregiver registers and sees "Something went wrong" because there's no way to create a care circle from the UI. Medications and appointments have full backend CRUD but only read-only frontend display. Patients see only chat + mood chart, with no visibility into the coordination layer (boards, meds, appointments, care team). The backend is feature-rich; the frontend is incomplete.

## Goal

Make every existing backend feature accessible and usable from the browser. A primary caregiver can register, set up a care circle, manage medications and appointments, and coordinate via shared boards. A patient lands on a dashboard that shows their wellness state at a glance and can collaborate on boards, log medication adherence, and request appointment changes.

## Sub-phases

### Phase 10a — Caregiver Completes the Loop

#### 1. Care Circle Setup Flow

**Trigger:** Caregiver with no circles sees the empty state page.

**UI:** "Set up a care circle" button on the empty state. Launches a two-step flow:

**Step 1 — Connect a patient** (two cards):
- **"Link existing patient"** — email input, system looks up the patient's user account (`GET /api/auth/...` or new lookup endpoint), creates circle with caregiver as `primary_caregiver`.
- **"Set up for someone new"** — name input (email optional). System creates a patient record + placeholder user account, creates circle. Patient can claim the account later.

**Step 2 — Confirmation** — circle created, dashboard loads with the patient.

**Backend:**
- **Link path:** New `GET /api/users/lookup?email=...` endpoint (caregiver-only). Returns `{user_id, patient_id, role}` if user exists with role `user`. 404 if not found or not a patient. Then `POST /api/circles` with that `patient_id`.
- **Create-new path:** New `POST /api/patients` endpoint (caregiver-only). Creates a patient record + placeholder user account (random password, `is_active=true`). Returns `{patient_id, user_id}`. Then `POST /api/circles` with that `patient_id`. The patient claims their account later by registering with the same email (register endpoint detects existing placeholder and updates password instead of creating a duplicate).

**Components:**
- `CircleSetupWizard.tsx` — stepped form (new)
- Update `CaregiverDashboard.tsx` empty state to render the wizard

#### 2. Medication CRUD Forms

**Current state:** `CaregiverDashboard.tsx` renders a read-only medication list from the overview endpoint.

**Add:**
- **Add form** — inline expandable form below the med list. Fields: name (text), dosage (text), frequency (select: daily/twice daily/weekly/as needed), prescriber (text, optional), start date (date). Calls `POST /patients/{patient_id}/medications`.
- **Edit** — click med row to expand with pre-filled editable fields. Calls `PATCH /patients/{patient_id}/medications/{med_id}`.
- **Discontinue** — button on each med, soft-deletes (`active=false`). Discontinued meds in a collapsible "Past medications" section.
- **Interaction warning** — if `POST` returns interaction data from `MedicationManagerAgent`, display an inline alert with the warning before confirming.

**Backend:** No changes needed. `POST/PATCH/DELETE /patients/{patient_id}/medications` endpoints exist.

**Components:**
- `MedicationCard.tsx` — replaces the read-only list (new, or refactor inline section from CaregiverDashboard)
- `MedicationForm.tsx` — add/edit form (new)

#### 3. Appointment CRUD Forms

**Same pattern as medications:**

- **Schedule** — inline form: title, date, time, notes (optional). `POST /patients/{patient_id}/appointments`.
- **Edit** — expand row, edit fields. `PATCH`.
- **Cancel** — sets status to "cancelled", grays out. Does not delete.
- **Upcoming/past split** — sorted by date, past in collapsible section.

**Backend:** No changes needed. CRUD endpoints exist.

**Components:**
- `AppointmentCard.tsx` — replaces read-only list (new)
- `AppointmentForm.tsx` — add/edit form (new)

#### 4. Board Items + Circle Members Polish

**Board items:**
- Ada suggestion badges more visible (highlight pending suggestions)
- Approve/reject flow clearer (distinct buttons, not just a generic checkbox)

**Circle members:**
- Add-member form already works
- Show role labels more prominently
- Light UI polish only, no functional changes

**No new components.** Modifications to existing `BoardItem.tsx`, `BoardView.tsx`, `CircleMembers.tsx`.

---

### Phase 10b — Patient Dashboard

#### 5. Dashboard Home

**Replaces** the current chat-first patient view as the default landing.

**Cards:**
- **"Talk to Ada"** — prominent top card. Shows last conversation snippet or "Start a new conversation." Click enters chat view.
- **Today's Overview** — mood trend, assessments due, wellness summary (from daily summary if available).
- **Medications** — active meds with "Mark as taken" checkboxes. Shows dosage and frequency.
- **Upcoming Appointments** — next 3-5 appointments. "Request change" button on each.
- **My Boards** — board items from the patient's circle. Can add items and check off completed ones.
- **My Care Team** — read-only list of circle members (name, role). Informational only.

**Components:**
- `PatientDashboard.tsx` — main container (new)
- `TalkToAdaCard.tsx` — chat entry point (new)
- `PatientMedicationsCard.tsx` — meds with adherence logging (new)
- `PatientAppointmentsCard.tsx` — appointments with change request (new)
- `PatientBoardsCard.tsx` — board items, collaborative (new)
- `CareTeamCard.tsx` — read-only circle members (new)

#### 6. Navigation Refactor

**Current:** sidebar with sessions + Chat/Mood toggle.

**New:** top-level navigation: Home | Chat | Mood

- `view` state type extends from `'chat' | 'mood'` to `'home' | 'chat' | 'mood'`
- Default view changes from `'chat'` to `'home'`
- Sidebar (session list) only visible in `'chat'` view
- No React Router needed — state-based routing pattern extends cleanly

**Files modified:**
- `App.tsx` — add `'home'` to View type, render `PatientDashboard` for home, add nav bar
- `App.css` — nav bar styles

#### 7. Collaborative Features

**Medication adherence:**
- Patient taps "Taken" on a medication → creates a log entry
- Caregiver dashboard shows adherence status (taken/missed/pending for today)
- New table: `medication_logs (id, medication_id, patient_id, taken_at, status)`
- New endpoint: `POST /patients/{patient_id}/medications/{med_id}/log`
- New endpoint: `GET /patients/{patient_id}/medications/{med_id}/logs?date=...`

**Appointment change requests:**
- Patient taps "Request change" → enters a note → flags the appointment
- Caregiver sees flag + note on their dashboard
- Add `change_requested: bool` + `change_note: text` columns to appointments table
- `PATCH /patients/{patient_id}/appointments/{appt_id}` already exists, just needs to accept these fields

**Board collaboration:**
- Patient can add items to boards in their circle
- Patient can check off items (mark complete)
- Patient sees Ada suggestions pending approval
- Backend already supports this — board endpoints are circle-scoped, patient is a circle member
- Need to verify patient auth works for board endpoints (currently only tested with caregiver role)

#### 8. Backend Additions Summary

| Change | Type | Endpoint/Table |
|--------|------|----------------|
| `medication_logs` table | New table | `(id, medication_id, patient_id, taken_at, status)` |
| Log medication taken | New endpoint | `POST /patients/{id}/medications/{mid}/log` |
| Get medication logs | New endpoint | `GET /patients/{id}/medications/{mid}/logs` |
| Appointment change request fields | Schema change | Add `change_requested`, `change_note` to appointments |
| Patient lookup by email | New endpoint | `GET /api/users/lookup?email=...` (for circle setup) |
| Patient access to board endpoints | Verify/fix | Ensure circle membership check works for patient role |

---

## Data Flow

### Caregiver Setup Flow
```
Register (role=caregiver) → Empty state → "Set up care circle"
  → Link existing patient (email lookup → create circle)
  → OR Create new patient (name → create patient + circle)
  → Dashboard loads with patient data
```

### Medication Adherence Loop
```
Caregiver adds med → POST /medications → MedicationManagerAgent checks interactions
  → Patient sees med on dashboard → taps "Taken" → POST /medications/{id}/log
  → Caregiver dashboard shows adherence status
```

### Appointment Change Request
```
Caregiver schedules → POST /appointments
  → Patient sees on dashboard → taps "Request change" → enters note
  → PATCH /appointments/{id} {change_requested: true, change_note: "..."}
  → Caregiver dashboard shows flag + note
```

## Testing Strategy

### Phase 10a Tests
- Circle setup: integration test — register caregiver → create circle (both paths) → verify dashboard loads
- Medication CRUD: unit tests for new form components + integration test for full add/edit/discontinue flow
- Appointment CRUD: same pattern as medications
- Board/member polish: verify existing integration tests still pass

### Phase 10b Tests
- Patient dashboard: unit tests for each card component
- Navigation: verify view switching, default to home
- Medication adherence: integration test — add med → log taken → verify log endpoint returns data
- Appointment change request: integration test — schedule → request change → verify flag set
- Board collaboration: integration test — patient adds item, checks off item via board endpoints

### E2E Verification
Full product loop (manual): register patient → chat with Ada → register caregiver → set up circle → add medication → patient marks taken → caregiver sees adherence.

## Non-Goals
- Push notifications / email notifications (future)
- Medication reminders on a schedule (future)
- Real appointment calendar sync (Google, Outlook)
- Mobile app / PWA
- Multi-tenancy
