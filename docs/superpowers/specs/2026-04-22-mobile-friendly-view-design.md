# Mobile-friendly view polish — design

**Date:** 2026-04-22
**Status:** approved (inline), ready to implement
**Closes:** GitHub issue #55 (partially — MEDIUM items become follow-ups)

## Context

Ada's UI was built desktop-first. AppShell has mobile/desktop layouts via `matchMedia` (< 768px), but several card-dense views don't reflow correctly on 375px / 414px viewports. This PR addresses the CRITICAL + HIGH items from the mobile audit. MEDIUM items (tiny chart fonts, badge visibility, OnboardingFlow spinner) stay open under #55 as lower-priority follow-ups.

## Goals

1. Dashboards (patient + caregiver) render usably at 375px viewport — no locked 2-column grids.
2. Settings tab renders without crushed labels or negative horizontal overflow.
3. Chat bubbles size correctly on narrow viewports.
4. Caregiver dashboard header saves space when it wraps.
5. `App.css` carries responsive rules matching AppShell's breakpoint (< 768px).

## Non-goals

- MEDIUM punch-list items (deferred — issue #55 stays open for those).
- No full-system design overhaul.
- No new breakpoints beyond what AppShell already uses.
- No frontend routing changes.

## The 8 fixes

### CRITICAL 1 — Dashboard grids

**Files:** `web/src/components/PatientDashboard.tsx:~106`, `web/src/components/CaregiverDashboard.tsx:~110`

Both use `gridTemplateColumns: 'repeat(2, 1fr)'`, which forces 2 columns at 375px where each card ends up ~180px wide and text wraps awkwardly.

Fix: replace with `repeat(auto-fit, minmax(280px, 1fr))` — the same pattern `ProgressReport.tsx:137` already uses successfully. 1 column on mobile, 2+ on wider screens.

### CRITICAL 2 — Mobile media queries in App.css

**File:** `web/src/App.css`

Only 2 `@media (max-width: 767px)` rules exist today. Add a consolidated mobile block near the end of the file (before the board list / PWA rules already there) covering:
- SettingsPage padding: reduce to `var(--space-md)` on mobile
- Chart label / legend font sizes: bump floor to `var(--size-sm)` (14px) if they're currently 12–13px — ONLY for the charts that are clearly too small. Don't touch all font sizes globally.
- Any currently-problematic widths identified during implementation

Scope: add only the rules needed to address the other fixes. Don't speculatively pad this block.

### CRITICAL 3 — SettingsPage org-section minWidth crush

**File:** `web/src/components/SettingsPage.tsx:~466-492`

Member email/role labels have `minWidth: '80px'`. On 375px the form becomes left-weighted and the input beside them is unusable.

Fix: remove the `minWidth: '80px'` on each label, OR make it `minWidth: 'auto'` on mobile via `@media` in App.css. Simpler path: just remove it — content width naturally works.

### HIGH 4 — ChatMessage maxWidth

**File:** `web/src/components/ChatMessage.tsx:~40`

`maxWidth: '80%'` is fine on desktop; on 375px + padding, bubbles still touch 90%+ of viewport, causing mid-word line breaks.

Fix: bump to `85%` (default) + reduce to `90%` at mobile-breakpoint via inline media-query-in-CSS approach (move to a CSS class with a media query in App.css, or use calc). Prefer the CSS-class route if the component already has a className available.

### HIGH 5 — Sidebar width coordination

**Files:** `web/src/components/AppShell.tsx:~77` + `web/src/App.css` (sidebar rule, if present)

AppShell sets sidebar `width: '240px'` in its inline style. App.css may define a separate `--sidebar-width: 280px` variable. Mismatch is fragile — if the JS fallback doesn't run (SSR, slow hook), desktop rules apply on mobile.

Fix: audit both and align. Drop the App.css sidebar rule if it's unused, OR set it to match 240px. Keep one source of truth.

### HIGH 6 — SettingsPage padding math

**File:** `web/src/components/SettingsPage.tsx:~83`

`maxWidth: '480px'` + `padding: var(--space-lg)` (24px each side) = the inner content is 432px. On a 375px phone with 413px safe area, margins go negative.

Fix: on mobile (via App.css media query), reduce page padding to `var(--space-md)` (16px).

### HIGH 7 — ScreeningHistory score badge

**File:** `web/src/components/ScreeningHistory.tsx:~226`

Score label is `fontSize: '11px'`. Readable but cramped when `minWidth: '52px'` packs it into the badge on narrow widths.

Fix: bump the label to `var(--size-xs)` but ensure that token is at least 12px on mobile. If `--size-xs` is already 11px globally, switch the specific badge to `var(--size-sm)` (14px) on mobile only.

### HIGH 8 — CaregiverDashboard header flex gap

**File:** `web/src/components/CaregiverDashboard.tsx:~69,79`

Header has `flexWrap: 'wrap'` but `gap: var(--space-md)` (16px) stays the same wrapped or not. On mobile the wasted vertical space between stacked title and action buttons looks gappy.

Fix: on mobile, reduce to `var(--space-sm)` (8px) via CSS class + media query.

## Scope guardrails

- Do NOT touch backend.
- Do NOT refactor the responsive system beyond what's in scope.
- Do NOT modify tests (except to update any that reference the hardcoded 2-col grid).
- Touch targets must stay ≥ 44px — no regressions.
- Don't break desktop rendering — desktop viewport visual regressions are a blocker.

## Verification

1. Frontend tests stay green: `npm test -- --run`.
2. Typecheck clean: `npm run typecheck`.
3. Production build clean: `npm run build` produces `dist/sw.js`.
4. **Manual viewport test** (user on phone via `http://100.92.157.18:5173`, or via DevTools device emulation at 375px):
   - Patient dashboard: cards stack vertically, readable
   - Caregiver dashboard: cards stack, header doesn't waste space
   - Settings: org section doesn't horizontally overflow, form usable
   - Chat: bubbles don't force mid-word breaks
   - Desktop (≥ 768px): no visual regressions

## Follow-up (NOT in this PR, tracked under #55)

- Chart label sizes (MoodChart, AdherenceDonut)
- TopBar notification badge legibility
- OnboardingFlow spinner scaling
- ClinicianNotes metadata font sizes
