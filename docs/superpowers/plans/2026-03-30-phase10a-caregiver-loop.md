# Phase 10a — Caregiver Completes the Loop: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable a primary caregiver to register, create a care circle, manage medications and appointments, and coordinate care — all from the browser.

**Architecture:** Frontend-heavy phase. Backend already has full CRUD for medications, appointments, and circles. We add 2 new backend endpoints (user lookup + caregiver-initiated patient creation), then build frontend forms that call existing endpoints. New components follow the established pattern: typed API client functions in `client.ts`, Pydantic models on the backend, React components with inline forms.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Vite (frontend), existing CSS custom properties

**Spec:** `docs/superpowers/specs/2026-03-30-phase10-close-the-loop-design.md`

---

### Task 1: Backend — User Lookup Endpoint

**Files:**
- Modify: `ada/api/routes/circles.py`
- Test: `tests/unit/test_circle_routes.py`

The circle setup wizard needs to look up patients by email. Add a dedicated endpoint to `circles.py` (circle-scoped, not auth-scoped — only caregivers setting up circles need this).

- [ ] **Step 1: Write the failing test**

```python
# In tests/unit/test_circle_routes.py — add at end of file

@pytest.mark.asyncio
async def test_lookup_user_by_email_found(client, state):
    """GET /api/circles/lookup?email=... returns user info when found."""
    # Create a patient user
    user_id = str(uuid.uuid4())
    patient_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()
    await state.create_patient({
        "id": patient_id, "name": "Test Patient", "dob": None,
        "preferences": "{}", "emergency_contact": None,
        "caregiver_id": None, "created_at": now,
    })
    await state.create_user({
        "id": user_id, "email": "patient@example.com",
        "hashed_password": "hashed", "role": "user",
        "patient_id": patient_id, "created_at": now, "is_active": 1,
    })
    resp = client.get("/api/circles/lookup", params={"email": "patient@example.com"},
                      headers={"Authorization": f"Bearer {caregiver_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "patient@example.com"
    assert data["patient_id"] == patient_id
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_lookup_user_by_email_not_found(client, state):
    """GET /api/circles/lookup?email=... returns 404 when not found."""
    resp = client.get("/api/circles/lookup", params={"email": "nobody@example.com"},
                      headers={"Authorization": f"Bearer {caregiver_token}"})
    assert resp.status_code == 404
```

Note: Adapt fixture/token patterns from existing tests in this file. The test may need a `caregiver_token` fixture — check how existing circle tests authenticate.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_circle_routes.py::test_lookup_user_by_email_found -v`
Expected: FAIL — endpoint does not exist (404 from test client)

- [ ] **Step 3: Implement the endpoint**

Add to `ada/api/routes/circles.py` after the existing imports:

```python
@router.get("/lookup")
async def lookup_user_by_email(
    email: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Look up a user by email for circle setup. Caregiver-only."""
    if current_user.role not in ("caregiver", "clinician", "admin"):
        raise HTTPException(status_code=403, detail="Caregivers only")
    state = request.app.state.state_manager
    user = await state.get_user_by_email(email)
    if not user or user.get("role") != "user":
        raise HTTPException(status_code=404, detail="Patient not found")
    return {
        "user_id": user["id"],
        "email": user["email"],
        "patient_id": user.get("patient_id"),
        "role": user["role"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_circle_routes.py -v`
Expected: All pass including new tests

- [ ] **Step 5: Commit**

```bash
git add ada/api/routes/circles.py tests/unit/test_circle_routes.py
git commit -m "feat(circles): add user lookup endpoint for circle setup"
```

---

### Task 2: Backend — Caregiver-Initiated Patient Creation

**Files:**
- Modify: `ada/api/routes/circles.py`
- Test: `tests/unit/test_circle_routes.py`

When a caregiver creates a circle for someone new (not yet registered), we need to create a patient record and a placeholder user account in one step.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_create_patient_for_circle(client, state):
    """POST /api/circles/create-with-patient creates patient + circle."""
    resp = client.post("/api/circles/create-with-patient",
                       json={"patient_name": "Mom", "patient_email": "mom@example.com"},
                       headers={"Authorization": f"Bearer {caregiver_token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["patient_name"] == "Mom"
    assert "circle_id" in data
    assert "patient_id" in data
    # Verify circle exists with caregiver as primary
    circle = await state.get_care_circle_by_patient(data["patient_id"])
    assert circle is not None


@pytest.mark.asyncio
async def test_create_patient_for_circle_links_existing(client, state):
    """POST /api/circles/create-with-patient with existing patient email links them."""
    # Pre-create a patient user
    user_id = str(uuid.uuid4())
    patient_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()
    await state.create_patient({
        "id": patient_id, "name": "Existing", "dob": None,
        "preferences": "{}", "emergency_contact": None,
        "caregiver_id": None, "created_at": now,
    })
    await state.create_user({
        "id": user_id, "email": "existing@example.com",
        "hashed_password": "hashed", "role": "user",
        "patient_id": patient_id, "created_at": now, "is_active": 1,
    })
    resp = client.post("/api/circles/create-with-patient",
                       json={"patient_name": "Existing", "patient_email": "existing@example.com"},
                       headers={"Authorization": f"Bearer {caregiver_token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["patient_id"] == patient_id  # Linked to existing
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_circle_routes.py::test_create_patient_for_circle -v`
Expected: FAIL — endpoint does not exist

- [ ] **Step 3: Implement the endpoint**

Add to `ada/api/routes/circles.py`:

```python
from pydantic import BaseModel

class CreateWithPatientRequest(BaseModel):
    patient_name: str
    patient_email: str | None = None

@router.post("/create-with-patient", status_code=201)
async def create_circle_with_patient(
    body: CreateWithPatientRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a care circle for a patient. If patient_email matches an existing
    user account, link to that patient. Otherwise, create a new patient record
    and placeholder user account."""
    if current_user.role not in ("caregiver", "clinician", "admin"):
        raise HTTPException(status_code=403, detail="Caregivers only")

    state = request.app.state.state_manager
    now = datetime.now(tz=timezone.utc).isoformat()

    # Check if patient already exists by email
    patient_id = None
    if body.patient_email:
        existing_user = await state.get_user_by_email(body.patient_email)
        if existing_user and existing_user.get("role") == "user":
            patient_id = existing_user.get("patient_id")

    # Create new patient if not found
    if not patient_id:
        patient_id = str(uuid.uuid4())
        await state.create_patient({
            "id": patient_id,
            "name": body.patient_name,
            "dob": None,
            "preferences": "{}",
            "emergency_contact": None,
            "caregiver_id": None,
            "created_at": now,
        })
        # Create placeholder user account if email provided
        if body.patient_email:
            placeholder_user_id = str(uuid.uuid4())
            await state.create_user({
                "id": placeholder_user_id,
                "email": body.patient_email,
                "hashed_password": hash_password(str(uuid.uuid4())),  # random, unclaimed
                "role": "user",
                "patient_id": patient_id,
                "created_at": now,
                "is_active": 1,
            })

    # Check patient doesn't already have a circle
    existing_circle = await state.get_care_circle_by_patient(patient_id)
    if existing_circle:
        raise HTTPException(status_code=409, detail="Patient already has a care circle")

    # Create circle + add caregiver as primary
    circle_id = str(uuid.uuid4())
    await state.create_care_circle(circle_id, patient_id)
    member_id = str(uuid.uuid4())
    await state.add_circle_member(member_id, circle_id, current_user.id,
                                  "primary_caregiver", added_by=current_user.id)

    return {
        "circle_id": circle_id,
        "patient_id": patient_id,
        "patient_name": body.patient_name,
    }
```

Add the `hash_password` import at top of file:
```python
from ada.api.auth import hash_password
```

Add missing imports (`uuid`, `datetime`):
```python
import uuid
from datetime import datetime, timezone
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_circle_routes.py -v`
Expected: All pass

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All 914+ pass, 0 regressions

- [ ] **Step 6: Commit**

```bash
git add ada/api/routes/circles.py tests/unit/test_circle_routes.py
git commit -m "feat(circles): add create-with-patient endpoint for caregiver setup"
```

---

### Task 3: Frontend — Medication & Appointment API Client Functions

**Files:**
- Modify: `web/src/api/client.ts`
- Modify: `web/src/types/index.ts`

Add typed API functions for medication and appointment CRUD. These call existing backend endpoints.

- [ ] **Step 1: Add full medication and appointment types to `types/index.ts`**

The existing `CaregiverMedication` and `CaregiverAppointment` types are read-only summaries from the overview endpoint. Add full types matching the backend models:

```typescript
// Add after existing CaregiverMedication/CaregiverAppointment types

export interface Medication {
  id: string
  patient_id: string
  name: string
  dosage: string | null
  frequency: string | null
  start_date: string | null
  end_date: string | null
  notes: string | null
  prescribed_by: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export interface MedicationCreate {
  name: string
  dosage?: string
  frequency?: string
  start_date?: string
  prescribed_by?: string
  notes?: string
}

export interface MedicationUpdate {
  name?: string
  dosage?: string
  frequency?: string
  start_date?: string
  end_date?: string
  active?: boolean
  prescribed_by?: string
  notes?: string
}

export interface MedicationCreateResponse extends Medication {
  interaction_warning?: string
}

export interface Appointment {
  id: string
  patient_id: string
  title: string
  description: string | null
  scheduled_at: string
  duration_minutes: number
  appointment_type: string
  status: string
  provider_name: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface AppointmentCreate {
  title: string
  scheduled_at: string
  description?: string
  duration_minutes?: number
  appointment_type?: string
  provider_name?: string
  notes?: string
}

export interface AppointmentUpdate {
  title?: string
  scheduled_at?: string
  description?: string
  duration_minutes?: number
  status?: string
  provider_name?: string
  notes?: string
}

export interface UserLookup {
  user_id: string
  email: string
  patient_id: string | null
  role: string
}

export interface CreateWithPatientResponse {
  circle_id: string
  patient_id: string
  patient_name: string
}
```

- [ ] **Step 2: Add API functions to `client.ts`**

Add after existing board functions:

```typescript
// --- Medications ---

export function listMedications(patientId: string, activeOnly = false): Promise<Medication[]> {
  const params = activeOnly ? '?active_only=true' : ''
  return request<Medication[]>(`/patients/${patientId}/medications${params}`)
}

export function createMedication(patientId: string, body: MedicationCreate): Promise<MedicationCreateResponse> {
  return request<MedicationCreateResponse>(`/patients/${patientId}/medications`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateMedication(patientId: string, medId: string, body: MedicationUpdate): Promise<Medication> {
  return request<Medication>(`/patients/${patientId}/medications/${medId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deactivateMedication(patientId: string, medId: string): Promise<void> {
  return request<void>(`/patients/${patientId}/medications/${medId}`, { method: 'DELETE' })
}

// --- Appointments ---

export function listAppointments(patientId: string, status?: string): Promise<Appointment[]> {
  const params = status ? `?status=${status}` : ''
  return request<Appointment[]>(`/patients/${patientId}/appointments${params}`)
}

export function createAppointment(patientId: string, body: AppointmentCreate): Promise<Appointment> {
  return request<Appointment>(`/patients/${patientId}/appointments`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateAppointment(patientId: string, apptId: string, body: AppointmentUpdate): Promise<Appointment> {
  return request<Appointment>(`/patients/${patientId}/appointments/${apptId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteAppointment(patientId: string, apptId: string): Promise<void> {
  return request<void>(`/patients/${patientId}/appointments/${apptId}`, { method: 'DELETE' })
}

// --- Circle Setup ---

export function lookupUserByEmail(email: string): Promise<UserLookup> {
  return request<UserLookup>(`/circles/lookup?email=${encodeURIComponent(email)}`)
}

export function createCircleWithPatient(body: { patient_name: string; patient_email?: string }): Promise<CreateWithPatientResponse> {
  return request<CreateWithPatientResponse>('/circles/create-with-patient', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
```

Add the new type imports at top of `client.ts`:

```typescript
import type {
  // ... existing imports ...
  Medication, MedicationCreate, MedicationCreateResponse, MedicationUpdate,
  Appointment, AppointmentCreate, AppointmentUpdate,
  UserLookup, CreateWithPatientResponse,
} from '../types'
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd web && node_modules/.bin/tsc --noEmit`
Expected: No new errors (1 pre-existing error in useChat.ts is OK)

- [ ] **Step 4: Commit**

```bash
git add web/src/types/index.ts web/src/api/client.ts
git commit -m "feat(frontend): add medication, appointment, and circle setup API client functions"
```

---

### Task 4: Frontend — CircleSetupWizard Component

**Files:**
- Create: `web/src/components/CircleSetupWizard.tsx`
- Modify: `web/src/components/CaregiverDashboard.tsx`
- Modify: `web/src/App.css`

- [ ] **Step 1: Create the wizard component**

```typescript
// web/src/components/CircleSetupWizard.tsx

import { useState, type FormEvent } from 'react'
import { lookupUserByEmail, createCircleWithPatient } from '../api/client'

interface CircleSetupWizardProps {
  onComplete: () => void
}

type Step = 'choose' | 'link' | 'create' | 'done'

export function CircleSetupWizard({ onComplete }: CircleSetupWizardProps) {
  const [step, setStep] = useState<Step>('choose')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleLink(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const user = await lookupUserByEmail(email)
      if (!user.patient_id) {
        setError('This user does not have a patient profile.')
        return
      }
      await createCircleWithPatient({ patient_name: email, patient_email: email })
      setStep('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Patient not found. Check the email address.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await createCircleWithPatient({
        patient_name: name,
        patient_email: newEmail || undefined,
      })
      setStep('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create care circle.')
    } finally {
      setSubmitting(false)
    }
  }

  if (step === 'done') {
    return (
      <div className="circle-wizard">
        <div className="circle-wizard__done">
          <h2>Care circle created</h2>
          <p>You can now manage medications, appointments, and shared boards.</p>
          <button className="circle-wizard__btn" onClick={onComplete} type="button">
            Go to dashboard
          </button>
        </div>
      </div>
    )
  }

  if (step === 'link') {
    return (
      <div className="circle-wizard">
        <h2>Link an existing patient</h2>
        <p>Enter the email address they used to register with Ada.</p>
        <form className="circle-wizard__form" onSubmit={handleLink}>
          <label className="circle-wizard__label" htmlFor="link-email">Patient email</label>
          <input
            id="link-email"
            className="circle-wizard__input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="patient@example.com"
            required
            disabled={submitting}
          />
          {error && <p className="circle-wizard__error">{error}</p>}
          <div className="circle-wizard__actions">
            <button type="button" className="circle-wizard__btn circle-wizard__btn--secondary"
                    onClick={() => { setStep('choose'); setError(null) }}>Back</button>
            <button type="submit" className="circle-wizard__btn" disabled={submitting || !email}>
              {submitting ? 'Linking...' : 'Link patient'}
            </button>
          </div>
        </form>
      </div>
    )
  }

  if (step === 'create') {
    return (
      <div className="circle-wizard">
        <h2>Set up for someone new</h2>
        <p>Create a profile for the person you are caring for.</p>
        <form className="circle-wizard__form" onSubmit={handleCreate}>
          <label className="circle-wizard__label" htmlFor="create-name">Their name</label>
          <input
            id="create-name"
            className="circle-wizard__input"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Mom"
            required
            disabled={submitting}
          />
          <label className="circle-wizard__label" htmlFor="create-email">Their email (optional)</label>
          <input
            id="create-email"
            className="circle-wizard__input"
            type="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="They can claim their account later"
            disabled={submitting}
          />
          {error && <p className="circle-wizard__error">{error}</p>}
          <div className="circle-wizard__actions">
            <button type="button" className="circle-wizard__btn circle-wizard__btn--secondary"
                    onClick={() => { setStep('choose'); setError(null) }}>Back</button>
            <button type="submit" className="circle-wizard__btn" disabled={submitting || !name}>
              {submitting ? 'Creating...' : 'Create care circle'}
            </button>
          </div>
        </form>
      </div>
    )
  }

  // Default: choose step
  return (
    <div className="circle-wizard">
      <h2>Set up a care circle</h2>
      <p>A care circle connects you with the person you are caring for.</p>
      <div className="circle-wizard__options">
        <button className="circle-wizard__option" onClick={() => setStep('link')} type="button">
          <strong>Link an existing patient</strong>
          <span>They already have an Ada account</span>
        </button>
        <button className="circle-wizard__option" onClick={() => setStep('create')} type="button">
          <strong>Set up for someone new</strong>
          <span>Create a profile for them</span>
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add CSS for the wizard**

Add to `web/src/App.css` near the `.cg-dashboard__empty` styles:

```css
/* Circle Setup Wizard */
.circle-wizard {
  max-width: 480px;
  margin: 2rem auto;
  padding: 2rem;
}
.circle-wizard h2 {
  margin: 0 0 0.5rem;
  font-size: 1.25rem;
}
.circle-wizard p {
  margin: 0 0 1.5rem;
  color: var(--color-text-secondary, #6b7280);
}
.circle-wizard__options {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.circle-wizard__option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 1.25rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  background: var(--color-surface, #fff);
  cursor: pointer;
  text-align: left;
}
.circle-wizard__option:hover {
  border-color: var(--color-primary, #6366f1);
}
.circle-wizard__option strong {
  font-size: 1rem;
}
.circle-wizard__option span {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
}
.circle-wizard__form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.circle-wizard__label {
  font-size: 0.875rem;
  font-weight: 500;
}
.circle-wizard__input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  font-size: 1rem;
}
.circle-wizard__error {
  color: var(--color-error, #ef4444);
  font-size: 0.875rem;
}
.circle-wizard__actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.5rem;
}
.circle-wizard__btn {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: var(--radius-md, 8px);
  background: var(--color-primary, #6366f1);
  color: #fff;
  font-size: 0.875rem;
  cursor: pointer;
}
.circle-wizard__btn:hover {
  opacity: 0.9;
}
.circle-wizard__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.circle-wizard__btn--secondary {
  background: transparent;
  color: var(--color-text-secondary, #6b7280);
  border: 1px solid var(--color-border, #e5e7eb);
}
.circle-wizard__done {
  text-align: center;
}
```

- [ ] **Step 3: Integrate wizard into CaregiverDashboard empty state**

In `web/src/components/CaregiverDashboard.tsx`, replace the empty state block (the `if (!selectedCircle)` section) with the wizard:

Add import at top:
```typescript
import { CircleSetupWizard } from './CircleSetupWizard'
```

Replace the `!selectedCircle` block:
```typescript
  if (!selectedCircle) {
    return (
      <div className="cg-dashboard">
        <header className="cg-dashboard__header">
          <div>
            <h1 className="cg-dashboard__title">Ada Caregiver Dashboard</h1>
          </div>
          <button className="cg-dashboard__sign-out" onClick={onLogout} type="button">
            Sign out
          </button>
        </header>
        <CircleSetupWizard onComplete={() => refresh()} />
      </div>
    )
  }
```

The `refresh` function comes from `useCircles()`. Update the destructure:
```typescript
const { circles, selectedCircle, selectCircle, refresh } = useCircles()
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd web && node_modules/.bin/tsc --noEmit`
Expected: No new errors

- [ ] **Step 5: Commit**

```bash
git add web/src/components/CircleSetupWizard.tsx web/src/components/CaregiverDashboard.tsx web/src/App.css
git commit -m "feat(frontend): add care circle setup wizard for new caregivers"
```

---

### Task 5: Frontend — MedicationCard Component

**Files:**
- Create: `web/src/components/MedicationCard.tsx`
- Modify: `web/src/components/CaregiverDashboard.tsx`
- Modify: `web/src/App.css`

Replaces the inline read-only medication list in the dashboard with a full CRUD card.

- [ ] **Step 1: Create the MedicationCard component**

```typescript
// web/src/components/MedicationCard.tsx

import { useState, useEffect, useCallback, type FormEvent } from 'react'
import {
  listMedications, createMedication, updateMedication, deactivateMedication,
} from '../api/client'
import type { Medication, MedicationCreate } from '../types'

interface MedicationCardProps {
  patientId: string
}

const FREQUENCY_OPTIONS = ['daily', 'twice daily', 'weekly', 'as needed']

export function MedicationCard({ patientId }: MedicationCardProps) {
  const [meds, setMeds] = useState<Medication[]>([])
  const [showPast, setShowPast] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  // Form state
  const [formName, setFormName] = useState('')
  const [formDosage, setFormDosage] = useState('')
  const [formFrequency, setFormFrequency] = useState('daily')
  const [formPrescriber, setFormPrescriber] = useState('')

  const fetchMeds = useCallback(async () => {
    try {
      const all = await listMedications(patientId)
      setMeds(all)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load medications')
    }
  }, [patientId])

  useEffect(() => { fetchMeds() }, [fetchMeds])

  function resetForm() {
    setFormName('')
    setFormDosage('')
    setFormFrequency('daily')
    setFormPrescriber('')
    setShowAdd(false)
    setEditingId(null)
    setWarning(null)
  }

  function startEdit(med: Medication) {
    setEditingId(med.id)
    setFormName(med.name)
    setFormDosage(med.dosage ?? '')
    setFormFrequency(med.frequency ?? 'daily')
    setFormPrescriber(med.prescribed_by ?? '')
    setShowAdd(false)
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setWarning(null)
    try {
      const body: MedicationCreate = {
        name: formName,
        dosage: formDosage || undefined,
        frequency: formFrequency || undefined,
        prescribed_by: formPrescriber || undefined,
      }
      const result = await createMedication(patientId, body)
      if (result.interaction_warning) {
        setWarning(result.interaction_warning)
      }
      resetForm()
      await fetchMeds()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add medication')
    }
  }

  async function handleUpdate(e: FormEvent) {
    e.preventDefault()
    if (!editingId) return
    setError(null)
    try {
      await updateMedication(patientId, editingId, {
        name: formName,
        dosage: formDosage || undefined,
        frequency: formFrequency || undefined,
        prescribed_by: formPrescriber || undefined,
      })
      resetForm()
      await fetchMeds()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update medication')
    }
  }

  async function handleDiscontinue(medId: string) {
    setError(null)
    try {
      await deactivateMedication(patientId, medId)
      await fetchMeds()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to discontinue medication')
    }
  }

  const activeMeds = meds.filter((m) => m.active)
  const pastMeds = meds.filter((m) => !m.active)

  function renderForm(onSubmit: (e: FormEvent) => void, submitLabel: string) {
    return (
      <form className="med-card__form" onSubmit={onSubmit}>
        <input className="med-card__input" type="text" placeholder="Medication name"
               value={formName} onChange={(e) => setFormName(e.target.value)} required />
        <input className="med-card__input" type="text" placeholder="Dosage (e.g. 10mg)"
               value={formDosage} onChange={(e) => setFormDosage(e.target.value)} />
        <select className="med-card__input" value={formFrequency}
                onChange={(e) => setFormFrequency(e.target.value)}>
          {FREQUENCY_OPTIONS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <input className="med-card__input" type="text" placeholder="Prescribed by (optional)"
               value={formPrescriber} onChange={(e) => setFormPrescriber(e.target.value)} />
        <div className="med-card__form-actions">
          <button type="button" className="med-card__btn med-card__btn--secondary"
                  onClick={resetForm}>Cancel</button>
          <button type="submit" className="med-card__btn" disabled={!formName}>{submitLabel}</button>
        </div>
      </form>
    )
  }

  return (
    <div className="med-card">
      <div className="med-card__header">
        <h3>Medications</h3>
        {!showAdd && !editingId && (
          <button className="med-card__btn" onClick={() => setShowAdd(true)} type="button">+ Add</button>
        )}
      </div>
      {error && <p className="med-card__error">{error}</p>}
      {warning && <p className="med-card__warning">{warning}</p>}
      {showAdd && renderForm(handleAdd, 'Add medication')}
      {activeMeds.length === 0 && !showAdd && <p className="med-card__empty">No active medications</p>}
      {activeMeds.map((med) => (
        <div key={med.id} className="med-card__item">
          {editingId === med.id ? (
            renderForm(handleUpdate, 'Save changes')
          ) : (
            <>
              <div className="med-card__item-info" onClick={() => startEdit(med)}>
                <strong>{med.name}</strong>
                {med.dosage && <span>{med.dosage}</span>}
                {med.frequency && <span className="med-card__freq">{med.frequency}</span>}
              </div>
              <button className="med-card__btn med-card__btn--danger" type="button"
                      onClick={() => handleDiscontinue(med.id)}>Discontinue</button>
            </>
          )}
        </div>
      ))}
      {pastMeds.length > 0 && (
        <>
          <button className="med-card__toggle" onClick={() => setShowPast(!showPast)} type="button">
            {showPast ? 'Hide' : 'Show'} past medications ({pastMeds.length})
          </button>
          {showPast && pastMeds.map((med) => (
            <div key={med.id} className="med-card__item med-card__item--inactive">
              <div className="med-card__item-info">
                <strong>{med.name}</strong>
                {med.dosage && <span>{med.dosage}</span>}
              </div>
              <span className="med-card__badge med-card__badge--inactive">Discontinued</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add CSS for MedicationCard**

Add to `web/src/App.css`:

```css
/* Medication Card */
.med-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}
.med-card__header h3 { margin: 0; }
.med-card__form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-md, 8px);
}
.med-card__input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  font-size: 0.875rem;
}
.med-card__form-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}
.med-card__btn {
  padding: 0.35rem 0.75rem;
  border: none;
  border-radius: var(--radius-md, 8px);
  background: var(--color-primary, #6366f1);
  color: #fff;
  font-size: 0.8rem;
  cursor: pointer;
}
.med-card__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.med-card__btn--secondary {
  background: transparent;
  color: var(--color-text-secondary, #6b7280);
  border: 1px solid var(--color-border, #e5e7eb);
}
.med-card__btn--danger {
  background: transparent;
  color: var(--color-error, #ef4444);
  border: 1px solid var(--color-error, #ef4444);
}
.med-card__item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}
.med-card__item-info {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
  cursor: pointer;
}
.med-card__item-info:hover { opacity: 0.7; }
.med-card__freq {
  font-size: 0.8rem;
  color: var(--color-text-secondary, #6b7280);
}
.med-card__item--inactive { opacity: 0.5; }
.med-card__badge--inactive {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #6b7280);
}
.med-card__toggle {
  background: none;
  border: none;
  color: var(--color-primary, #6366f1);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.5rem 0;
}
.med-card__error { color: var(--color-error, #ef4444); font-size: 0.8rem; }
.med-card__warning { color: #f59e0b; font-size: 0.8rem; }
.med-card__empty { color: var(--color-text-secondary, #6b7280); font-size: 0.875rem; }
```

- [ ] **Step 3: Replace inline medications section in CaregiverDashboard**

In `CaregiverDashboard.tsx`, add import:
```typescript
import { MedicationCard } from './MedicationCard'
```

Replace the inline medications section (the `<section>` block around lines 244-260 that renders `data.medications.map(...)`) with:
```typescript
<section className="cg-dashboard__card">
  <MedicationCard patientId={selectedCircle.patient_id} />
</section>
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd web && node_modules/.bin/tsc --noEmit`
Expected: No new errors

- [ ] **Step 5: Commit**

```bash
git add web/src/components/MedicationCard.tsx web/src/components/CaregiverDashboard.tsx web/src/App.css
git commit -m "feat(frontend): add MedicationCard with full CRUD for caregiver dashboard"
```

---

### Task 6: Frontend — AppointmentCard Component

**Files:**
- Create: `web/src/components/AppointmentCard.tsx`
- Modify: `web/src/components/CaregiverDashboard.tsx`
- Modify: `web/src/App.css`

Same pattern as MedicationCard. Replaces the read-only appointment list.

- [ ] **Step 1: Create the AppointmentCard component**

```typescript
// web/src/components/AppointmentCard.tsx

import { useState, useEffect, useCallback, type FormEvent } from 'react'
import {
  listAppointments, createAppointment, updateAppointment, deleteAppointment,
} from '../api/client'
import type { Appointment, AppointmentCreate } from '../types'

interface AppointmentCardProps {
  patientId: string
}

export function AppointmentCard({ patientId }: AppointmentCardProps) {
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [showPast, setShowPast] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Form state
  const [formTitle, setFormTitle] = useState('')
  const [formDate, setFormDate] = useState('')
  const [formTime, setFormTime] = useState('')
  const [formNotes, setFormNotes] = useState('')

  const fetchAppointments = useCallback(async () => {
    try {
      const all = await listAppointments(patientId)
      setAppointments(all)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load appointments')
    }
  }, [patientId])

  useEffect(() => { fetchAppointments() }, [fetchAppointments])

  function resetForm() {
    setFormTitle('')
    setFormDate('')
    setFormTime('')
    setFormNotes('')
    setShowAdd(false)
    setEditingId(null)
  }

  function startEdit(appt: Appointment) {
    setEditingId(appt.id)
    setFormTitle(appt.title)
    const dt = new Date(appt.scheduled_at)
    setFormDate(dt.toISOString().split('T')[0])
    setFormTime(dt.toTimeString().slice(0, 5))
    setFormNotes(appt.notes ?? '')
    setShowAdd(false)
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const body: AppointmentCreate = {
        title: formTitle,
        scheduled_at: new Date(`${formDate}T${formTime || '09:00'}`).toISOString(),
        notes: formNotes || undefined,
      }
      await createAppointment(patientId, body)
      resetForm()
      await fetchAppointments()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to schedule appointment')
    }
  }

  async function handleUpdate(e: FormEvent) {
    e.preventDefault()
    if (!editingId) return
    setError(null)
    try {
      await updateAppointment(patientId, editingId, {
        title: formTitle,
        scheduled_at: new Date(`${formDate}T${formTime || '09:00'}`).toISOString(),
        notes: formNotes || undefined,
      })
      resetForm()
      await fetchAppointments()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update appointment')
    }
  }

  async function handleCancel(apptId: string) {
    setError(null)
    try {
      await updateAppointment(patientId, apptId, { status: 'cancelled' })
      await fetchAppointments()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel appointment')
    }
  }

  const now = new Date()
  const upcoming = appointments.filter((a) => a.status !== 'cancelled' && new Date(a.scheduled_at) >= now)
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
  const past = appointments.filter((a) => a.status === 'cancelled' || new Date(a.scheduled_at) < now)
    .sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime())

  function formatDate(iso: string): string {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  }

  function renderForm(onSubmit: (e: FormEvent) => void, submitLabel: string) {
    return (
      <form className="appt-card__form" onSubmit={onSubmit}>
        <input className="appt-card__input" type="text" placeholder="Appointment title"
               value={formTitle} onChange={(e) => setFormTitle(e.target.value)} required />
        <div className="appt-card__row">
          <input className="appt-card__input" type="date" value={formDate}
                 onChange={(e) => setFormDate(e.target.value)} required />
          <input className="appt-card__input" type="time" value={formTime}
                 onChange={(e) => setFormTime(e.target.value)} />
        </div>
        <textarea className="appt-card__input" placeholder="Notes (optional)" rows={2}
                  value={formNotes} onChange={(e) => setFormNotes(e.target.value)} />
        <div className="appt-card__form-actions">
          <button type="button" className="med-card__btn med-card__btn--secondary"
                  onClick={resetForm}>Cancel</button>
          <button type="submit" className="med-card__btn"
                  disabled={!formTitle || !formDate}>{submitLabel}</button>
        </div>
      </form>
    )
  }

  return (
    <div className="appt-card">
      <div className="med-card__header">
        <h3>Appointments</h3>
        {!showAdd && !editingId && (
          <button className="med-card__btn" onClick={() => setShowAdd(true)} type="button">+ Schedule</button>
        )}
      </div>
      {error && <p className="med-card__error">{error}</p>}
      {showAdd && renderForm(handleAdd, 'Schedule')}
      {upcoming.length === 0 && !showAdd && <p className="med-card__empty">No upcoming appointments</p>}
      {upcoming.map((appt) => (
        <div key={appt.id} className="med-card__item">
          {editingId === appt.id ? (
            renderForm(handleUpdate, 'Save changes')
          ) : (
            <>
              <div className="med-card__item-info" onClick={() => startEdit(appt)}>
                <strong>{appt.title}</strong>
                <span className="med-card__freq">{formatDate(appt.scheduled_at)}</span>
              </div>
              <button className="med-card__btn med-card__btn--danger" type="button"
                      onClick={() => handleCancel(appt.id)}>Cancel</button>
            </>
          )}
        </div>
      ))}
      {past.length > 0 && (
        <>
          <button className="med-card__toggle" onClick={() => setShowPast(!showPast)} type="button">
            {showPast ? 'Hide' : 'Show'} past / cancelled ({past.length})
          </button>
          {showPast && past.map((appt) => (
            <div key={appt.id} className="med-card__item med-card__item--inactive">
              <div className="med-card__item-info">
                <strong>{appt.title}</strong>
                <span className="med-card__freq">{formatDate(appt.scheduled_at)}</span>
              </div>
              <span className="med-card__badge--inactive">{appt.status}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add CSS**

Add to `web/src/App.css`:

```css
/* Appointment Card (reuses .med-card__* for shared patterns) */
.appt-card__form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-md, 8px);
}
.appt-card__input {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  font-size: 0.875rem;
  font-family: inherit;
}
.appt-card__row {
  display: flex;
  gap: 0.5rem;
}
.appt-card__form-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}
```

- [ ] **Step 3: Replace inline appointments section in CaregiverDashboard**

Add import:
```typescript
import { AppointmentCard } from './AppointmentCard'
```

Replace the inline appointments section (the `<section>` block around lines 263-287 that renders `data.appointments.map(...)`) with:
```typescript
<section className="cg-dashboard__card">
  <AppointmentCard patientId={selectedCircle.patient_id} />
</section>
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd web && node_modules/.bin/tsc --noEmit`
Expected: No new errors

- [ ] **Step 5: Commit**

```bash
git add web/src/components/AppointmentCard.tsx web/src/components/CaregiverDashboard.tsx web/src/App.css
git commit -m "feat(frontend): add AppointmentCard with full CRUD for caregiver dashboard"
```

---

### Task 7: Frontend — Board Items & Circle Members Polish

**Files:**
- Modify: `web/src/components/BoardItem.tsx`
- Modify: `web/src/components/AdaSuggestionBadge.tsx`
- Modify: `web/src/App.css`

Light polish: make Ada suggestions more prominent, improve approve/reject UX.

- [ ] **Step 1: Read current AdaSuggestionBadge**

Read `web/src/components/AdaSuggestionBadge.tsx` to understand current implementation before modifying.

- [ ] **Step 2: Improve suggestion visibility**

Modify `AdaSuggestionBadge.tsx` — update the badge to be more prominent with distinct approve/dismiss buttons:

```typescript
// Replace the return JSX with clearer actions
export function AdaSuggestionBadge({ onApprove, onDismiss }: AdaSuggestionBadgeProps) {
  return (
    <div className="ada-badge">
      <span className="ada-badge__label">Ada suggestion</span>
      <button className="ada-badge__approve" onClick={onApprove} type="button"
              title="Approve this suggestion">Approve</button>
      <button className="ada-badge__dismiss" onClick={onDismiss} type="button"
              title="Dismiss this suggestion">Dismiss</button>
    </div>
  )
}
```

- [ ] **Step 3: Add/update CSS for suggestion badges**

Add to `web/src/App.css`:

```css
/* Ada Suggestion Badge - enhanced */
.ada-badge {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.ada-badge__label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-primary, #6366f1);
  font-weight: 600;
}
.ada-badge__approve {
  padding: 0.2rem 0.5rem;
  border: 1px solid #22c55e;
  border-radius: var(--radius-md, 8px);
  background: transparent;
  color: #22c55e;
  font-size: 0.75rem;
  cursor: pointer;
}
.ada-badge__approve:hover { background: #22c55e; color: #fff; }
.ada-badge__dismiss {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  background: transparent;
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.75rem;
  cursor: pointer;
}
.ada-badge__dismiss:hover { background: var(--color-error, #ef4444); color: #fff; border-color: var(--color-error, #ef4444); }
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd web && node_modules/.bin/tsc --noEmit`
Expected: No new errors

- [ ] **Step 5: Commit**

```bash
git add web/src/components/AdaSuggestionBadge.tsx web/src/App.css
git commit -m "feat(frontend): improve Ada suggestion badge with distinct approve/dismiss buttons"
```

---

### Task 8: Integration Test — Full Caregiver Setup Flow

**Files:**
- Create: `tests/integration/test_caregiver_setup_flow.py`

End-to-end integration test: register caregiver → create circle (both paths) → verify dashboard data loads.

- [ ] **Step 1: Write the integration test**

```python
"""
Integration test: caregiver registers, creates a care circle, and can
fetch dashboard data for the linked patient.

Tests both the "link existing patient" and "create new patient" paths.
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from ada.core.config import get_config
from ada.core.state import StateManager
from ada.api.auth import hash_password


@pytest.fixture
async def state():
    config = get_config()
    sm = StateManager(config, db_path=":memory:")
    await sm.initialize()
    yield sm


@pytest.fixture
async def app(state):
    from ada.api.app import create_app
    application = create_app()
    application.state.state_manager = state
    application.state.config = get_config()
    return application


@pytest.fixture
async def client(app):
    from httpx import ASGITransport
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def register_and_login(client: AsyncClient, email: str, password: str, role: str = "user") -> str:
    """Register a user and return an access token."""
    await client.post("/api/auth/register", json={"email": email, "password": password, "role": role})
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_caregiver_setup_create_new_patient(client, state):
    """Caregiver creates a circle for a new patient."""
    token = await register_and_login(client, "cg@test.com", "TestPass1234", "caregiver")
    headers = {"Authorization": f"Bearer {token}"}

    # No circles initially
    resp = await client.get("/api/circles/my", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # Create circle with new patient
    resp = await client.post("/api/circles/create-with-patient",
                             json={"patient_name": "Mom", "patient_email": "mom@test.com"},
                             headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["patient_name"] == "Mom"
    patient_id = data["patient_id"]

    # Now has one circle
    resp = await client.get("/api/circles/my", headers=headers)
    assert resp.status_code == 200
    circles = resp.json()
    assert len(circles) == 1

    # Can fetch overview for this patient
    resp = await client.get(f"/api/caregiver/overview?patient_id={patient_id}", headers=headers)
    assert resp.status_code == 200
    overview = resp.json()
    assert overview["patient"]["name"] == "Mom"


@pytest.mark.asyncio
async def test_caregiver_setup_link_existing_patient(client, state):
    """Caregiver links to an existing patient account."""
    # Patient registers first
    patient_token = await register_and_login(client, "patient@test.com", "TestPass1234", "user")

    # Caregiver registers
    cg_token = await register_and_login(client, "cg2@test.com", "TestPass1234", "caregiver")
    headers = {"Authorization": f"Bearer {cg_token}"}

    # Lookup patient
    resp = await client.get("/api/circles/lookup", params={"email": "patient@test.com"}, headers=headers)
    assert resp.status_code == 200
    lookup = resp.json()
    assert lookup["role"] == "user"
    assert lookup["patient_id"] is not None

    # Create circle linked to existing patient
    resp = await client.post("/api/circles/create-with-patient",
                             json={"patient_name": "Patient", "patient_email": "patient@test.com"},
                             headers=headers)
    assert resp.status_code == 201
    assert resp.json()["patient_id"] == lookup["patient_id"]


@pytest.mark.asyncio
async def test_caregiver_can_manage_medications_after_setup(client, state):
    """After creating a circle, caregiver can add medications."""
    token = await register_and_login(client, "cg3@test.com", "TestPass1234", "caregiver")
    headers = {"Authorization": f"Bearer {token}"}

    # Create circle
    resp = await client.post("/api/circles/create-with-patient",
                             json={"patient_name": "Dad"},
                             headers=headers)
    patient_id = resp.json()["patient_id"]

    # Add medication
    resp = await client.post(f"/api/patients/{patient_id}/medications",
                             json={"name": "Aspirin", "dosage": "81mg", "frequency": "daily"},
                             headers=headers)
    assert resp.status_code == 201
    assert resp.json()["name"] == "Aspirin"

    # List medications
    resp = await client.get(f"/api/patients/{patient_id}/medications", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
```

- [ ] **Step 2: Run integration test**

Run: `.venv/bin/python -m pytest tests/integration/test_caregiver_setup_flow.py -v`
Expected: All 3 tests pass

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All tests pass (914 + new tests), 0 regressions

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_caregiver_setup_flow.py
git commit -m "test(integration): add caregiver setup flow tests for circle creation + med CRUD"
```

---

## Verification Checklist

After all tasks are complete:

1. **Backend tests:** `.venv/bin/python -m pytest tests/ -x -q` — all pass
2. **TypeScript:** `cd web && node_modules/.bin/tsc --noEmit` — no new errors
3. **Manual E2E:**
   - Register as caregiver → see setup wizard
   - "Set up for someone new" → enter name → circle created → dashboard loads
   - Add medication → see it in list → edit → discontinue → see in past
   - Schedule appointment → see it in list → edit → cancel → see in past
   - Board items: Ada suggestions show approve/dismiss buttons
4. **MASTER_PLAN.md:** Update Phase 10a status to `completed` with commit refs
