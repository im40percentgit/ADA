# Phase 5 — Caregiver Dashboard Design

**Date:** 2026-02-26
**Status:** Approved

## Context

Ada's backend has all the clinical data a caregiver needs: SOAP session summaries, crisis alerts, assessments (PHQ-9, GAD-7, WHO-5), medications, and appointments. The `patients.caregiver_id` column already exists but is unused. Phase 5 adds authorization scoping and a dedicated frontend dashboard for family member caregivers.

## User Decisions

- **Primary user:** Family member (non-clinical) — warm, jargon-free language
- **Notifications:** In-dashboard only — no email/push infrastructure
- **Multi-patient:** One patient per caregiver — no patient switcher
- **Privacy:** SOAP summaries only — no access to chat messages

## Architecture

**Approach:** Separate caregiver SPA route in the existing React app. When `user.role === "caregiver"`, App.tsx renders `CaregiverDashboard` instead of Chat/Mood views. Data from a single aggregation endpoint.

### Backend Changes

**Role addition:**
- Add `"caregiver"` to `Role = Literal["user", "clinician", "admin", "caregiver"]` in `ada/models/user.py`

**Authorization:**
- New dependency `require_caregiver_access(patient_id)` — verifies authenticated user's ID matches `patient.caregiver_id`

**Caregiver-patient link:**
- Admin assigns via existing `PATCH /api/patients/{id}` setting `caregiver_id`
- No self-service linking in Phase 5

**New endpoint:**

```
GET /api/caregiver/overview
```

Returns aggregated dashboard data:
```json
{
  "patient": { "name", "dob", "emergency_contact" },
  "recent_sessions": [
    { "id", "started_at", "ended_at", "summary": { "subjective", "assessment", "plan", "key_topics", "risk_flags" } }
  ],
  "crisis_alerts": [ { "severity", "timestamp", "escalation_action" } ],
  "assessments": {
    "phq9": [ { "total_score", "severity", "timestamp" } ],
    "gad7": [ "..." ],
    "who5": [ "..." ]
  },
  "medications": [ { "name", "dosage", "frequency", "active" } ],
  "appointments": [ { "title", "scheduled_at", "status" } ]
}
```

Privacy: `trigger_text` excluded from crisis alerts. No chat messages exposed.

### Frontend — Dashboard Layout

**Routing:** `App.tsx` — if `currentUser.role === "caregiver"`, render `<CaregiverDashboard />`. No sidebar.

**Components (5 new):**

| Component | Purpose |
|-----------|---------|
| `CaregiverDashboard.tsx` | Container — fetches `/api/caregiver/overview`, polls every 60s |
| `StatusCard.tsx` | "How They're Doing" — friendly sentence from SOAP assessment + mood trend |
| `AlertsCard.tsx` | Crisis alerts with severity. Red background for HIGH/CRITICAL |
| `SessionsCard.tsx` | Recent sessions — SOAP plan + key_topics, human-readable. Max 5 |
| `WellbeingChart.tsx` | WHO-5 line chart over time (Recharts) |

Medications and appointments rendered as sections within `CaregiverDashboard`.

**Language translation (clinical -> family-friendly):**
- `assessment` -> "How They're Doing"
- `plan` -> "Next Steps"
- `key_topics` -> "Topics Discussed"
- `risk_flags` -> "Things to Watch" (only if non-empty)
- severity HIGH -> "Needs Attention", CRITICAL -> "Urgent"

### Layout

```
+--------------------------------------------------+
|  Ada Caregiver Dashboard           [Logout]      |
|  Caring for: Mom (Jane Doe)                      |
+--------------------------------------------------+
|  [How They're Doing]  [Alerts]                   |
|  [Recent Sessions -- last 5]                     |
|  [Wellbeing Trend]     [Medications]             |
|  [Upcoming Appointments]                         |
+--------------------------------------------------+
```

## Testing

**Backend:**
- Unit: overview endpoint response shape, trigger_text exclusion
- Unit: authorization — caregiver accesses own patient, denied for others
- Integration: register caregiver -> create patient -> populate data -> verify overview

**Frontend:**
- CaregiverDashboard: mount with mock data, verify all cards render
- StatusCard: various SOAP data -> friendly language
- AlertsCard: no alerts -> "No recent alerts"; HIGH -> red styling
- WellbeingChart: WHO-5 data points -> chart renders

**E2E:**
1. Register caregiver, create linked patient
2. Generate session data (SOAP, crisis, meds, appointments)
3. Login as caregiver -> dashboard renders with all data
4. Login as wrong caregiver -> 403

## Out of Scope

- Self-service caregiver-patient linking
- Email/push notifications
- Multi-patient support
- Real-time WebSocket updates (60s polling sufficient)
- Chat message access
