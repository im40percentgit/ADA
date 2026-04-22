# Mobile-friendly view polish — MEDIUM + cleanup

**Date:** 2026-04-22
**Status:** approved (inline), ready to implement
**Closes:** GitHub issue #55 (final cleanup after CRITICAL + HIGH PR)

## Context

The CRITICAL + HIGH mobile fixes landed at `da4b1cf`. This PR closes out #55 by addressing the remaining MEDIUM items from the audit plus two practical mobile polish items the prior implementer surfaced. It also folds in the orphan design doc `2026-04-22-mobile-friendly-view-design.md` that missed staging in the prior merge.

## Goals

1. TopBar notification badge readable on mobile (was 18px — too small for phone distance).
2. OnboardingFlow spinner sized correctly on mobile (was 10×10, nearly invisible).
3. Chart/secondary-content fonts >= 14px on mobile (MoodChart labels, AdherenceDonut legend, ClinicianNotes metadata).
4. Chat input respects iOS safe-area-inset-bottom so the input isn't hidden behind the home indicator on iPhone.
5. Commit the two orphan spec docs that missed staging on their merges.

## Non-goals

- No compact-mode sidebar toggle (future feature, not a polish item).
- No PWA splashscreen color (low impact; can be done later).
- No desktop visual changes.

## The fixes

### MEDIUM 1 — TopBar notification badge

**File:** `web/src/components/ui/TopBar.tsx` (around the badgeStyle definition, currently `fontSize: '10px'`, `width/height: '18px'`)

Add a CSS class `className="ada-topbar-badge"` to the badge span, then a media query in App.css:

```css
@media (max-width: 767px) {
  .ada-topbar-badge { font-size: 12px; width: 22px; height: 22px; }
}
```

Desktop stays 18px/10px (compact); mobile gets 22px/12px (thumb-distance readable).

### MEDIUM 2 — OnboardingFlow spinner

**File:** `web/src/components/onboarding/OnboardingFlow.tsx` (around line 131-132 where the spinner is `width: '10px', height: '10px'`)

The 10px spinner is tiny on both desktop and mobile. Bump to 20px globally — it's a loading indicator, should be visible. No media query needed.

Alternatively if the 10px is intentional for some inline context, wrap with `className="ada-onboarding-spinner"` and use a media query to bump only on mobile. Implementer's call — prefer the simpler global bump.

### MEDIUM 3 — Chart/metadata fonts

Three files with sub-14px fonts on secondary content:
- `web/src/components/MoodChart.tsx:~120` — chart label
- `web/src/components/charts/AdherenceDonut.tsx:~78` — legend text
- `web/src/components/ClinicianNotes.tsx:~134` — note metadata

For each, find the `fontSize: '12px'` or `fontSize: '13px'` and bump to `var(--size-sm)` (14px). If the chart library (e.g., recharts) requires a specific font size for axis labels, keep the desktop look but scale up on mobile via className + media query.

Prefer the simple direct bump unless it demonstrably breaks the chart layout.

### MEDIUM 4 — Chat input safe-area-inset

**File:** `web/src/components/Chat.tsx` (or the chat input subcomponent — find the bottom input wrapper)

On iOS PWA, the home indicator bar hides the bottom ~34px of the viewport. The chat input needs:

```ts
paddingBottom: 'calc(var(--space-md) + env(safe-area-inset-bottom, 0))'
```

Or via CSS class. Test that the input is reachable on iPhone in standalone-PWA mode (user will verify).

If the chat input is in a dedicated component file, add the style there. If it's inline in Chat.tsx, inline the change.

### Cleanup — fold in orphan spec docs

Two spec files exist untracked on main from prior brainstorming that missed their merges:
- `docs/superpowers/specs/2026-04-22-mobile-friendly-view-design.md` (CRITICAL + HIGH spec)
- `docs/superpowers/specs/2026-04-22-mobile-friendly-view-medium-design.md` (this file)

Stage both into this branch so the design history matches the code.

## Tests

- `npm test -- --run` — expect 531 pass.
- `npm run typecheck` — expect 0 errors.
- `npm run build` — expect clean + `dist/sw.js`.

## Verification

User verifies on their tailnet phone:
1. TopBar — notification badge readable from arm's-length.
2. Onboarding (if going through it fresh) — spinner visible while state loads.
3. MoodChart, AdherenceDonut legend, ClinicianNotes metadata — text readable without squinting.
4. Chat — input not hidden behind iPhone home indicator in PWA mode.

## Closes

Include `Closes #55` in the commit body — this completes the mobile-friendly view work.
