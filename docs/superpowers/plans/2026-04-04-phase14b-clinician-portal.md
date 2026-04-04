# Phase 14b — Clinician Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add goal-based treatment planning with automated progress tracking and prescribing notes for clinicians.

**Architecture:** Three new tables (treatment_plans, treatment_goals, treatment_interventions) plus prescribing_notes. Auto-progress via EventBus subscription on assessment completion. REST API for CRUD. Frontend components with Card-based UI matching the design system.

**Tech Stack:** Python/FastAPI, React/TypeScript, aiosqlite, existing UI component library, EventBus

**Design Spec:** `docs/superpowers/specs/2026-04-04-phase14b-clinician-portal-design.md`

---

## Task 1: Treatment Plans Backend

**Files:** Modify state.py (3 tables + CRUD), create treatment_plans.py route, create tests, register router.

- [ ] Add treatment_plans, treatment_goals, treatment_interventions tables to state.py schema. Add CRUD: create/get/list treatment plans, add/update goals, add/update interventions, get_goals_by_metric (for auto-progress).
- [ ] Add TreatmentGoalMetEvent to events.py.
- [ ] Create ada/api/routes/treatment_plans.py with all CRUD endpoints. Clinician role required for writes.
- [ ] Register router. Write tests. Commit: `feat(phase14b): add treatment plans backend with goal-based tracking`

## Task 2: Auto-Progress Tracking

**Files:** Create ada/agents/treatment_progress.py subscriber.

- [ ] Create EventBus subscriber that listens for AssessmentCompletedEvent. On event: find active treatment goals matching the assessment instrument. Update current_value. If goal met: update status, publish TreatmentGoalMetEvent.
- [ ] Write tests for progress tracking logic. Commit: `feat(phase14b): add auto-progress tracking for treatment goals`

## Task 3: Prescribing Notes Backend

**Files:** Create prescribing_notes.py route, add table to state.py, tests.

- [ ] Add prescribing_notes table to state.py + CRUD. Create route with POST/GET endpoints. Clinician role required.
- [ ] Write tests. Commit: `feat(phase14b): add prescribing notes backend`

## Task 4: Frontend Types + API + Components

**Files:** Types, API client, MSW, factories, TreatmentPlan.tsx, PrescribingNotes.tsx, tests.

- [ ] Add TypeScript types: TreatmentPlan, TreatmentGoal, TreatmentIntervention, PrescribingNote.
- [ ] Add API functions for all treatment plan + prescribing endpoints.
- [ ] Add MSW handlers + factories.
- [ ] Create TreatmentPlan.tsx: plan header, goals with progress bars, interventions, add goal/intervention forms.
- [ ] Create PrescribingNotes.tsx: timeline, add note form with type picker and medication selector.
- [ ] Write component tests. Commit: `feat(phase14b): add treatment plan and prescribing notes UI`

## Task 5: Navigation Integration

**Files:** App.tsx, CaregiverDashboard.tsx.

- [ ] Add treatment-plan and prescribing-notes to View type. Add routes. Add Treatment Plans section to clinician's dashboard view.
- [ ] Run all tests. Commit: `feat(phase14b): integrate clinician portal into navigation`
