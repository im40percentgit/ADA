# Phase 13b — Onboarding Flow

## Context

New users register and land on the dashboard with no guidance. They don't know what Ada can do, haven't set up their companion preferences, and (for caregivers) may not have created a care circle. Phase 13b adds a first-run onboarding experience that introduces the app, sets up the companion, and tours role-specific features.

## Structure

Five tasks:
1. Onboarding state backend
2. Companion setup screens (shared by all roles)
3. Patient feature tour
4. Caregiver feature tour
5. OnboardingFlow component + App.tsx integration

---

## 1. Onboarding State Backend

**Goal:** Track whether a user has completed onboarding.

### Database

Add `onboarding_status` column to `users` table:
```sql
ALTER TABLE users ADD COLUMN onboarding_status TEXT NOT NULL DEFAULT 'not_started'
  CHECK(onboarding_status IN ('not_started', 'in_progress', 'completed'));
```

Since SQLite doesn't support ALTER TABLE ADD COLUMN with CHECK constraints easily, instead add the column in the schema `CREATE TABLE` definition with the default. For existing users, they'll have `not_started` which is correct — they can dismiss the onboarding from the dashboard if they want.

### API Endpoints

- `GET /api/onboarding/status` — returns `{ "status": "not_started" | "in_progress" | "completed" }` for current user
- `PUT /api/onboarding/status` — accepts `{ "status": "in_progress" | "completed" }`, updates user record

### State Methods

- `get_onboarding_status(user_id) -> str`
- `set_onboarding_status(user_id, status) -> None`

---

## 2. Companion Setup Screens (Shared)

**Goal:** All users configure their companion during onboarding.

Four screens in sequence:

**Screen 1 — Welcome**
- Large heading: "Welcome to Ada"
- Subtitle: "Let's set up your personal wellness companion"
- Illustration: warm purple gradient circle with sparkle
- "Get Started" Button

**Screen 2 — Name Your Companion**
- Heading: "What would you like to call your companion?"
- Input field, pre-filled with "Ada"
- Preview text: "Hi! I'm {name}, and I'm here to support your wellness journey."
- "Next" Button

**Screen 3 — Choose Voice**
- Heading: "Choose {name}'s voice"
- Three option cards: Female, Male, Neutral
- Each with a play button for audio preview (optional — can be deferred if TTS preview is complex)
- "Next" Button

**Screen 4 — Choose Personality**
- Heading: "How should {name} communicate?"
- Three toggle rows: Warm↔Professional, Chatty↔Concise, Casual↔Formal
- Preview bubble showing how {name} would greet with current settings
- "Next" Button

All companion preferences saved via existing `PUT /api/companion/preferences` (from Phase 13a).

---

## 3. Patient Feature Tour

**Goal:** Introduce patients to Ada's key features.

Three screens after companion setup:

**Screen 5 — Chat**
- Heading: "Talk to {name} anytime"
- Description: "{name} is here for daily check-ins, wellness conversations, and emotional support. Just start a session and talk."
- Visual: mock chat bubble preview

**Screen 6 — Wellbeing Tracking**
- Heading: "Track your wellbeing"
- Description: "Regular assessments and mood tracking help you and your care team see how you're progressing over time."
- Visual: mini chart/sparkline preview

**Screen 7 — Cognitive Check-ins**
- Heading: "Cognitive check-ins"
- Description: "Interactive exercises test memory, attention, and reasoning. Fun tasks like pattern matching and clock reading help monitor cognitive health."
- Visual: mini pattern grid preview
- "Start Using {name}" Button (completes onboarding)

---

## 4. Caregiver Feature Tour

**Goal:** Introduce caregivers to their management tools.

Three screens after companion setup:

**Screen 5 — Care Circle**
- Heading: "Set up your care circle"
- Description: "A care circle connects you with the people you care for. Add patients, invite family members, and coordinate care together."
- "Set Up Circle" Button → launches existing CircleSetupWizard inline or marks for post-onboarding
- "Skip for now" link

**Screen 6 — Dashboard**
- Heading: "Your command center"
- Description: "See wellbeing scores, crisis alerts, session summaries, and medication adherence at a glance. Ada generates daily narratives so you're always in the loop."
- Visual: mini dashboard preview

**Screen 7 — Notifications**
- Heading: "Stay informed"
- Description: "Get push notifications for crisis alerts, daily summaries, and care circle activity. You control what you receive."
- "Enable Notifications" Button (triggers notification permission prompt)
- "Skip for now" link
- "Start Using Ada" Button (completes onboarding)

---

## 5. OnboardingFlow Component + Integration

### OnboardingFlow.tsx

Wizard component managing the step sequence:
- Progress dots at top (filled = completed, outlined = current, empty = future)
- Animated slide transitions between screens (CSS transform + opacity)
- Back button on all screens except first
- Step counter text ("Step 2 of 7")
- Props: `{ role: 'user' | 'caregiver'; companionName: string; onComplete: () => void }`

### Screen Components

Each screen is a focused component:
- `OnboardingWelcome.tsx`
- `OnboardingName.tsx`
- `OnboardingVoice.tsx`
- `OnboardingPersonality.tsx`
- `OnboardingChat.tsx` (patient)
- `OnboardingWellbeing.tsx` (patient)
- `OnboardingCognitive.tsx` (patient)
- `OnboardingCircle.tsx` (caregiver)
- `OnboardingDashboard.tsx` (caregiver)
- `OnboardingNotifications.tsx` (caregiver)

### App.tsx Integration

After login, check onboarding status:
1. Fetch `GET /api/onboarding/status`
2. If `not_started` or `in_progress`: render `<OnboardingFlow>` instead of `<AppShell>`
3. On completion: `PUT /api/onboarding/status` with `completed`, then render normal app
4. Add a "Skip onboarding" link for users who want to jump straight in

### Skip/Dismiss

- Every screen has implicit skip (just navigate to dashboard)
- Explicit "Skip onboarding" link in corner
- Skipping marks status as `completed` so it doesn't show again

---

## Verification Plan

1. **New user (patient):** Register → see onboarding → companion setup → patient tour → complete → dashboard
2. **New user (caregiver):** Register → see onboarding → companion setup → caregiver tour → complete → dashboard
3. **Skip:** Click "Skip onboarding" → goes to dashboard, doesn't show again on next login
4. **Returning user:** Login → goes straight to dashboard (onboarding completed)
5. **Companion prefs saved:** After onboarding, companion name/voice/personality reflected in chat

---

## Files Summary

### New Files
- `ada/api/routes/onboarding.py`
- `tests/unit/test_onboarding.py`
- `web/src/components/onboarding/OnboardingFlow.tsx`
- `web/src/components/onboarding/OnboardingWelcome.tsx`
- `web/src/components/onboarding/OnboardingName.tsx`
- `web/src/components/onboarding/OnboardingVoice.tsx`
- `web/src/components/onboarding/OnboardingPersonality.tsx`
- `web/src/components/onboarding/OnboardingChat.tsx`
- `web/src/components/onboarding/OnboardingWellbeing.tsx`
- `web/src/components/onboarding/OnboardingCognitive.tsx`
- `web/src/components/onboarding/OnboardingCircle.tsx`
- `web/src/components/onboarding/OnboardingDashboard.tsx`
- `web/src/components/onboarding/OnboardingNotifications.tsx`
- `web/test/components/OnboardingFlow.test.tsx`

### Modified Files
- `ada/core/state.py` — add onboarding_status to users schema + methods
- `ada/api/app.py` — register onboarding router
- `web/src/App.tsx` — onboarding gate before AppShell
- `web/src/types/index.ts` — OnboardingStatus type
- `web/src/api/client.ts` — onboarding API functions
- `web/test/msw/handlers.ts` — onboarding handlers
