# Phase 13b — Onboarding Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-run onboarding experience with companion setup and role-specific feature tours so new users understand Ada before hitting the dashboard.

**Architecture:** Onboarding status tracked server-side on the users table. App.tsx gates on status — showing OnboardingFlow instead of AppShell for incomplete users. Wizard component manages step sequence with role-branching after companion setup. Individual screen components are focused and simple.

**Tech Stack:** React/TypeScript (frontend), FastAPI (backend), existing UI component library (Card, Button, Input, Toggle, Badge)

**Design Spec:** `docs/superpowers/specs/2026-04-04-phase13b-onboarding-design.md`

---

## Task 1: Onboarding Backend

**Files:**
- Modify: `ada/core/state.py` — add onboarding_status column + methods
- Create: `ada/api/routes/onboarding.py`
- Create: `tests/unit/test_onboarding.py`
- Modify: `ada/api/app.py`

- [ ] Add `onboarding_status` column to the `users` CREATE TABLE in `_SCHEMA`. Default `'not_started'`, CHECK constraint `('not_started', 'in_progress', 'completed')`.
- [ ] Add `get_onboarding_status(user_id) -> str` and `set_onboarding_status(user_id, status) -> None` to StateManager.
- [ ] Create `ada/api/routes/onboarding.py`: `GET /api/onboarding/status` returns `{"status": "..."}` for current user, `PUT /api/onboarding/status` accepts `{"status": "in_progress"|"completed"}` and updates.
- [ ] Register router in `ada/api/app.py`.
- [ ] Write `tests/unit/test_onboarding.py`: test default status for new user, set/get round-trip, invalid status rejected.
- [ ] Run tests, commit: `feat(phase13b): add onboarding status backend`

---

## Task 2: Frontend Types + API + MSW

**Files:**
- Modify: `web/src/types/index.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/test/msw/handlers.ts`

- [ ] Add to `web/src/types/index.ts`: `export type OnboardingStatus = 'not_started' | 'in_progress' | 'completed'`
- [ ] Add API functions to `web/src/api/client.ts`: `getOnboardingStatus(): Promise<{status: OnboardingStatus}>`, `setOnboardingStatus(status: OnboardingStatus): Promise<void>`
- [ ] Add MSW handlers for GET/PUT onboarding status.
- [ ] Run tests, commit: `feat(phase13b): add onboarding types and API client functions`

---

## Task 3: Onboarding Screen Components

**Files:**
- Create: `web/src/components/onboarding/OnboardingWelcome.tsx`
- Create: `web/src/components/onboarding/OnboardingName.tsx`
- Create: `web/src/components/onboarding/OnboardingVoice.tsx`
- Create: `web/src/components/onboarding/OnboardingPersonality.tsx`
- Create: `web/src/components/onboarding/OnboardingChat.tsx`
- Create: `web/src/components/onboarding/OnboardingWellbeing.tsx`
- Create: `web/src/components/onboarding/OnboardingCognitive.tsx`
- Create: `web/src/components/onboarding/OnboardingCircle.tsx`
- Create: `web/src/components/onboarding/OnboardingDashboard.tsx`
- Create: `web/src/components/onboarding/OnboardingNotifications.tsx`

- [ ] Create directory `web/src/components/onboarding/`.
- [ ] Create all 10 screen components. Each is a simple presentational component:
  - Receives `onNext: () => void` and `onBack?: () => void` props
  - OnboardingName also receives `name: string, onNameChange: (name: string) => void`
  - OnboardingVoice: `voice: string, onVoiceChange: (voice: string) => void`
  - OnboardingPersonality: `personality: object, onPersonalityChange: (p: object) => void`
  - OnboardingCircle: `onSetupCircle?: () => void`
  - OnboardingNotifications: `onEnableNotifications?: () => void`
  - Each renders: heading, description, visual/illustration (simple styled div or emoji), action Button(s)
  - Uses Card, Button, Input, Toggle, Badge from `web/src/components/ui/`
  - Token-based styling throughout
- [ ] Commit: `feat(phase13b): add onboarding screen components for all steps`

---

## Task 4: OnboardingFlow Wizard + App.tsx Integration

**Files:**
- Create: `web/src/components/onboarding/OnboardingFlow.tsx`
- Create: `web/test/components/OnboardingFlow.test.tsx`
- Modify: `web/src/App.tsx`

- [ ] Create `OnboardingFlow.tsx`: wizard managing the step sequence.
  - Props: `{ role: 'user' | 'caregiver'; onComplete: () => void }`
  - State: `step` (number), companion prefs (`name`, `voice`, `personality`)
  - Step sequence for patients (role='user'): Welcome → Name → Voice → Personality → Chat → Wellbeing → Cognitive (7 steps)
  - Step sequence for caregivers: Welcome → Name → Voice → Personality → Circle → Dashboard → Notifications (7 steps)
  - Progress dots at top: array of circles, filled for completed steps, highlighted for current
  - Step counter: "Step {n} of 7"
  - Back button (hidden on step 1)
  - On final step submit: save companion prefs via `updateCompanionPreferences()`, call `setOnboardingStatus('completed')`, call `onComplete()`
  - "Skip onboarding" link in top-right corner → marks completed, calls onComplete
- [ ] Create `OnboardingFlow.test.tsx`: renders welcome screen, next advances step, progress dots update, skip link works, completion calls onComplete.
- [ ] Modify `App.tsx`: after login, fetch onboarding status. If not `completed`, render `<OnboardingFlow role={currentUser.role === 'caregiver' ? 'caregiver' : 'user'} onComplete={...} />` instead of `<AppShell>`. On complete, set local state to show AppShell. Add `onboardingComplete` state variable.
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase13b): add OnboardingFlow wizard with role-specific tours and App.tsx integration`

---

## Verification Checklist

- [ ] Backend: `python3 -m pytest tests/unit/test_onboarding.py -v` — all pass
- [ ] Frontend: `cd web && npx vitest run` — all pass
- [ ] New patient: register → onboarding starts → 7 steps → companion saved → dashboard
- [ ] New caregiver: register → onboarding starts → 7 steps → circle setup offered → dashboard
- [ ] Skip: click skip → goes to dashboard, doesn't show again
- [ ] Returning user: login → dashboard immediately
