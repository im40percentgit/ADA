# Caregiver nav regression + patient board click-through — design

**Date:** 2026-04-22
**Status:** approved (inline), ready to implement

## Context

Two UX bugs reported after the 2026-04-21 security sprint:

1. **Patients can't click into shared boards.** The patient dashboard renders each board as a non-interactive `<li>` (`PatientDashboard.tsx:678-683`) with no click handler. Always has been this way — not a regression.
2. **Caregivers can't navigate to Knowledge Map, Progress Report, or Cognitive Screenings.** Clicking the cards does nothing. Backend returns 200 on those endpoints when hit fresh. Root cause: `App.tsx` hoisted `useCircles()` to the top level ("Rules of Hooks") for the fix/ui-bugs PR. The hook fires once on mount. If the initial fetch fails or resolves before auth settles, `selectedCircle` stays `null` in App.tsx's instance. Every caregiver click then hits `if (!cgPatientId) return <CaregiverDashboard />` — navigation silently no-ops.

## Fixes

### Bug 1 — Patient boards clickable

**File:** `web/src/components/PatientDashboard.tsx` (around line 678-683).

The boards list currently renders:
```tsx
<li key={board.id} style={listItemStyle}>
  <span style={itemNameStyle}>{board.name}</span>
  <Badge variant="neutral">{board.board_type}</Badge>
</li>
```

Wire each item to open the board. Add a local `activeBoardId` state (mirrors how CaregiverDashboard does it), render `<BoardView>` when set, otherwise render the list. Each list item becomes a `<button>` (or stays `<li>` with a `<button>` inside) that calls `setActiveBoardId(board.id)`.

Use the same pattern CaregiverDashboard uses (its `BoardList` + `BoardView` toggle). Reuse the existing `BoardView` component — do not duplicate.

Touch targets must meet 44px minimum for mobile.

### Bug 2 — Caregiver nav via isolated `CaregiverApp`

**File:** `web/src/App.tsx` + new `web/src/components/CaregiverApp.tsx` (or extract within App.tsx as a sub-component — implementer's call based on file size).

Extract the caregiver branch (lines 189-245 of App.tsx) into a dedicated component that owns its own `useCircles()` call. App.tsx's job collapses to: check auth → check role → render `<CaregiverApp .../>` or patient branch.

New component shape:
```tsx
function CaregiverApp({
  currentUser, logout, view, setView,
  selectedSessionId, setSelectedSessionId,
  selectedSummaryDate, setSelectedSummaryDate,
  selectedScreeningId, setSelectedScreeningId,
  selectedPlanId, installBanner,
}: CaregiverAppProps) {
  const { selectedCircle } = useCircles()
  const cgPatientId = selectedCircle?.patient_id

  if (!cgPatientId) {
    return <div className="app">{installBanner}<CaregiverDashboard ... /></div>
  }

  // ... existing sub-view ternary chain
}
```

The benefits:
- `useCircles()` only runs when a caregiver is authenticated (component mounts AFTER auth gate).
- No more hoisted hook at App.tsx top level — remove that call entirely.
- The duplicate useCircles between App.tsx and CaregiverDashboard is reduced to one instance (CaregiverDashboard's own instance can stay as-is for now, matching the pre-existing comment).

Remove the `const { selectedCircle } = useCircles()` from App.tsx's top level + its "Called unconditionally" comment. Remove `import { useCircles } from './hooks/useCircles'` from App.tsx if no longer used.

## Non-goals

- Do NOT refactor useCircles into a React Context (separate larger task).
- Do NOT change the backend — authz is working correctly.
- Do NOT touch CaregiverDashboard's own `useCircles` instance.
- Do NOT add mobile-specific CSS beyond keeping touch targets >= 44px on the new patient board buttons.

## Tests

1. `npm test` (frontend) — expect the existing 531 pass count to hold.
2. Manual smoke in browser at `http://100.92.157.18:5173`:
   - **Patient:** log in → PatientDashboard shows boards → click a board → BoardView opens → back → returns to dashboard.
   - **Caregiver:** log in → CaregiverDashboard shows → click Knowledge Map → navigates to the knowledge graph view with patient data. Same for Progress Report and Cognitive Screenings.
   - Regression check: caregiver sign-out still works; patient settings tab still works.

## Verification

Live HTTP probe unnecessary for this PR — backend didn't change. The fixes are purely frontend state/render.
