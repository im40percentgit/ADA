# Settings tab wiring — design

**Date:** 2026-04-21
**Status:** approved (inline), ready to plan
**Scope:** small — finish wiring of an already-built feature

## Context

`SettingsPage.tsx` is fully built: Companion card (name, voice, personality), Account card (email + logout), Organization card. Backend route `ada/api/routes/companion.py` works. Hooks and tests exist. However, the patient Settings tab in `App.tsx` currently renders a `"Settings coming soon"` stub — the real component was never wired in.

In the prior session, sign-out was relocated to the patient TopBar so it's globally available. This makes the logout button inside SettingsPage's Account card redundant.

## Goal

Wire `SettingsPage` into the patient Settings tab and remove the redundant in-page logout.

## Non-goals

- No caregiver Settings tab (`CaregiverDashboard` keeps its own layout).
- No redesign of `SettingsPage`.
- No backend changes.

## Changes

### 1. `web/src/components/SettingsPage.tsx`

Remove the Log out button from the Account card. The simplest clean approach: drop the `onLogout` prop from `SettingsPageProps` entirely since nothing will call it.

- Delete `onLogout: () => void` from the interface.
- Delete the `<Button variant="ghost" onClick={onLogout} className="ada-settings-logout">Log out</Button>` JSX.
- Keep the email display and the rest of the Account card structure.

### 2. `web/src/App.tsx`

Replace the Settings stub (the "Settings coming soon" inline div) with:

```tsx
) : view === 'settings' ? (
  <SettingsPage email={currentUser?.email} patientId={patientId} />
)
```

Add the import:

```tsx
import { SettingsPage } from './components/SettingsPage'
```

No changes to the caregiver branch or any other view.

### 3. Tests

Existing `web/test/components/SettingsPage.test.tsx` references the logout button. Update it to:
- Remove `onLogout` from the mock props used in tests.
- Remove any assertion that clicks / finds the Log out button.
- Leave the rest of the coverage (companion form, organization, export, consent) intact.

## What stays unchanged

- `TopBar` Sign out button — remains the only sign-out path.
- Backend: `ada/api/routes/companion.py`, `useCompanionPreferences` hook.
- `CaregiverDashboard` and its separate sign-out button.

## Verification

1. Frontend test suite passes (expected 532/532 + any updated SettingsPage cases).
2. TypeScript clean (no new errors; the 3 pre-existing errors on main remain).
3. Live browser check: patient Settings tab renders the full SettingsPage; companion name saves; voice saves; personality toggles save; Account card shows email with no Log out button; Organization card loads.
4. Sign out still works only via TopBar.

## Open follow-ups (not in scope)

- Caregiver Settings (future: decide if caregivers get the Organization management card or a tailored variant).
- Password change / account management on the Account card.
- Removing the shared-deque nuance in the rate limiter (carryover from prior session).
