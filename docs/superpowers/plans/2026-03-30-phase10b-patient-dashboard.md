# Phase 10b — Patient Dashboard: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chat-first patient view with a dashboard home showing medications, appointments, boards, care team, and a prominent "Talk to Ada" entry point. Add collaborative features: medication adherence logging, appointment change requests, alert resolution.

**Architecture:** Backend adds 3 schema changes (medication_logs table, appointment change fields, alert status field) and 3 new endpoints. Frontend adds PatientDashboard container with card components, navigation refactor (home/chat/mood), and patient auto-membership in circles.

**Tech Stack:** Python/FastAPI, React/TypeScript/Vite, SQLite

**Spec:** docs/superpowers/specs/2026-03-30-phase10-close-the-loop-design.md (Phase 10b section)

---

## Task 1: Patient Auto-Membership in Circles

When a circle is created via create-with-patient, auto-add the patient as a member. When a patient registers and a circle exists for them, auto-add them.

**Files:**
- Modify: ada/api/routes/circles.py
- Modify: ada/api/routes/auth.py
- Test: tests/unit/test_circle_routes.py

## Task 2: Medication Adherence Logging

Add medication_logs table, StateManager CRUD, and REST endpoints for patients to log when they take medication.

**Files:**
- Modify: ada/core/state.py (new table + methods)
- Modify: ada/api/routes/medications.py (new endpoints)
- Test: tests/unit/test_medication_routes.py

Schema: medication_logs (id, medication_id, patient_id, taken_at, status CHECK(taken/skipped/missed), created_at)
Endpoints: POST /patients/{id}/medications/{mid}/log, GET /patients/{id}/medications/{mid}/logs

## Task 3: Appointment Change Requests + Alert Resolution

Add change_requested/change_note to appointments, add status/resolved_at/resolved_by to crisis_alerts. New alert update endpoint.

**Files:**
- Modify: ada/core/state.py (ALTER TABLE migrations)
- Modify: ada/models/appointment.py (new fields)
- Create: ada/api/routes/alerts.py (PATCH endpoint)
- Modify: ada/api/app.py (register alerts router)
- Test: tests/unit/ (new tests)

## Task 4: Frontend Types + API Client

Add MedicationLog, CrisisAlertFull types and API functions for medication logging, alert resolution, and patient endpoints.

**Files:**
- Modify: web/src/types/index.ts
- Modify: web/src/api/client.ts

## Task 5: PatientDashboard Component

Main patient dashboard with cards: Talk to Ada, Medications (with "Taken" button), Appointments (with "Request change"), Boards, Care Team, Mood Summary.

**Files:**
- Create: web/src/components/PatientDashboard.tsx
- Modify: web/src/App.css

Props: patientId, onNavigateToChat. Uses useCircles for board/team access. Each card is a section within the component.

## Task 6: Navigation Refactor

Extend View type to home/chat/mood. Default to home. Add 3-tab nav bar. Sidebar only visible in chat view. Render PatientDashboard for home.

**Files:**
- Modify: web/src/App.tsx
- Modify: web/src/App.css

## Task 7: Alert Resolution in Caregiver Dashboard

Add acknowledge/resolve buttons to AlertsCard. Active alerts show Acknowledge + Resolve. Resolved alerts show badge with timestamp.

**Files:**
- Modify: web/src/components/AlertsCard.tsx
- Modify: web/src/App.css

## Task 8: Integration Tests

Test patient circle access, medication logging, appointment change requests.

**Files:**
- Create: tests/integration/test_patient_dashboard_flow.py

## Verification Checklist

1. Backend tests: all pass
2. TypeScript: no new errors
3. Manual E2E: register patient, chat, register caregiver, create circle, add meds/appointments, login as patient, see dashboard, mark med taken, request appointment change, caregiver resolves alert
