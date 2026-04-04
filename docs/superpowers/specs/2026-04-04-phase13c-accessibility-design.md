# Phase 13c — Accessibility (WCAG 2.1 AA)

## Context

Ada serves patients with cognitive impairment, older adults, and anxious patients. Accessibility isn't optional — it's a clinical requirement. Phase 13c audits and fixes every component to meet WCAG 2.1 AA, the standard for web applications.

## Scope

Six areas, applied systematically across all components:

1. **Keyboard Navigation** — every interactive element reachable and operable via keyboard
2. **ARIA Labels** — screen reader announces all elements meaningfully
3. **Focus Management** — visible focus indicators, focus trapping in modals, skip links
4. **Color Contrast** — 4.5:1 minimum for text, 3:1 for large text and UI components
5. **Semantic HTML** — proper heading hierarchy, landmarks, lists, tables
6. **Motion & Timing** — respect prefers-reduced-motion, no time-dependent interactions without extensions

---

## 1. Keyboard Navigation

### Requirements
- All buttons, links, inputs, toggles, cards with onClick — focusable and activatable via Enter/Space
- Tab order follows visual order (no positive tabIndex)
- Custom interactive elements (PatternGrid cells, SequenceOrder items, graph nodes) — keyboard operable
- Bottom nav tabs — arrow key navigation within the tab bar
- Onboarding wizard — arrow keys for step navigation optional, Enter for Next/Back

### Specific Fixes
- **PatternGrid.tsx**: cells need `tabIndex={0}`, `role="gridcell"`, `onKeyDown` for Enter/Space to toggle selection, arrow keys to navigate grid
- **SequenceOrder.tsx**: items need `tabIndex={0}`, `role="option"`, Enter/Space to select, arrow keys to reorder
- **ClockTask.tsx**: options already buttons (good), ensure focus visible
- **KnowledgeGraph.tsx**: SVG nodes need `tabIndex={0}` within SVG `<g>` groups, Enter to select node, Escape to close detail panel
- **Card.tsx (clickable)**: already has onClick — add `role="button"`, `tabIndex={0}`, `onKeyDown` Enter/Space handler
- **Toggle.tsx**: underlying checkbox handles keyboard — verify
- **BottomNav.tsx**: add `role="tablist"`, tabs get `role="tab"`, arrow key navigation between tabs

---

## 2. ARIA Labels

### Requirements
- All images/icons have alt text or aria-hidden
- Form inputs have associated labels (htmlFor or aria-label)
- Dynamic content updates use aria-live regions
- Modals/panels use aria-modal, aria-labelledby
- Loading states use aria-busy
- Progress bars use aria-valuenow/min/max

### Specific Fixes
- **TopBar.tsx**: notification bell needs `aria-label="Notifications"`, avatar needs `aria-label="Profile"`
- **BottomNav.tsx**: `aria-label="Main navigation"` on nav, each tab `aria-selected`
- **ConnectionStatus.tsx**: `role="status"`, `aria-live="polite"` for reconnection messages
- **EmotionChip.tsx**: `aria-label` with emotion name + intensity
- **ProgressBar.tsx**: `role="progressbar"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"`
- **Badge.tsx**: if decorative, `aria-hidden`; if informational, ensure text is sufficient
- **Chat messages**: `aria-live="polite"` on message container for new messages
- **PatternGrid**: `role="grid"`, cells `role="gridcell"`, `aria-label="Cell {n}, {selected|unselected}"`
- **ScreeningTask**: `aria-label` describing the task type and domain
- **Assessment scores**: `aria-label="PHQ-9 score: 8, mild severity"`
- **Loading states**: `aria-busy="true"` on containers, `role="status"` with "Loading..." text

---

## 3. Focus Management

### Requirements
- Visible focus indicator on all interactive elements (already in base.css `:focus-visible`)
- Skip link: first focusable element, hidden until focused, jumps to main content
- Focus trap in slide-out panels (GraphDetailPanel)
- Return focus to trigger element when panel/modal closes
- Onboarding: focus moves to new step content on navigation

### Specific Fixes
- **AppShell.tsx**: add skip link `<a href="#main-content" class="skip-link">Skip to main content</a>` + `id="main-content"` on main content area
- **GraphDetailPanel.tsx**: trap focus within panel when open, Escape to close, return focus to triggering node
- **OnboardingFlow.tsx**: on step change, focus the step heading
- **SettingsPage.tsx**: focus first input on mount
- **base.css**: add `.skip-link` styles (visually hidden, visible on focus, positioned absolute)

---

## 4. Color Contrast

### Requirements
- Normal text: 4.5:1 minimum against background
- Large text (18px+ or 14px+ bold): 3:1 minimum
- UI components and graphical objects: 3:1 minimum against adjacent colors

### Audit
Current token palette needs verification:
- `--color-text-primary` (#fafaf9) on `--color-bg-base` (#1c1917): ~18:1 (excellent)
- `--color-text-secondary` (#e7e5e4) on `--color-bg-base` (#1c1917): ~14:1 (excellent)
- `--color-text-muted` (#a8a29e) on `--color-bg-base` (#1c1917): ~5.5:1 (passes AA)
- `--color-text-muted` (#a8a29e) on `--color-bg-card` (#292524): ~4.2:1 (borderline — may need adjustment)
- `--color-primary` (#7c3aed) on `--color-bg-base` (#1c1917): ~4.8:1 (passes AA for text)
- `--color-primary-light` (#a78bfa) on `--color-bg-base` (#1c1917): ~7.2:1 (excellent)
- Button text (white) on `--color-primary` (#7c3aed): ~5.7:1 (passes)

### Fix
- If muted text on card background fails: lighten `--color-text-muted` slightly or darken card background
- Verify all Badge variants meet contrast requirements
- Verify PatternGrid highlighted cells are distinguishable (not color-only — add pattern/border)

---

## 5. Semantic HTML

### Requirements
- One `<h1>` per page, heading levels don't skip
- Landmark elements: `<nav>`, `<main>`, `<header>`, `<footer>`, `<section>` with aria-label
- Lists use `<ul>`/`<ol>`/`<li>`
- Tables use `<table>` with headers (if any data tables exist)
- Forms use `<form>`, `<fieldset>`, `<legend>` where appropriate

### Specific Fixes
- **AppShell.tsx**: `<header>` for TopBar, `<nav>` for sidebar/bottom nav, `<main id="main-content">` for content
- **PatientDashboard/CaregiverDashboard**: wrap card sections in `<section aria-label="...">`
- **SessionSummary.tsx**: SOAP sections as `<article>` or `<section>` with headings
- **ScreeningResults.tsx**: task breakdown as `<ol>` list
- **OnboardingFlow.tsx**: steps as `<section aria-label="Step N of 7: {title}">`
- **Chat.tsx**: message list as `<ol>` or `<ul>` with role="log"
- Ensure no skipped heading levels (h1 → h3 without h2)

---

## 6. Motion & Timing

### Requirements
- Respect `prefers-reduced-motion`: disable animations, transitions
- PatternGrid display phase: provide extension option or remove time pressure
- No content that flashes more than 3 times per second

### Specific Fixes
- **base.css**: add `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; } }`
- **PatternGrid.tsx**: if prefers-reduced-motion, keep pattern visible until user explicitly dismisses (no auto-hide timer)
- **OnboardingFlow.tsx**: disable slide transitions when reduced motion preferred
- **ConnectionStatus.tsx**: no animation on reconnection banner when reduced motion

---

## Verification Plan

1. **Keyboard**: tab through entire app without mouse — every element reachable, operable, visible focus
2. **Screen reader**: test with browser screen reader (or inspect ARIA tree) — all elements announced meaningfully
3. **Contrast**: verify muted text on card passes 4.5:1 (adjust if needed)
4. **Skip link**: focus first element, see skip link, activate → jumps to main
5. **Focus trap**: open GraphDetailPanel → tab stays within panel → Escape closes → focus returns
6. **Reduced motion**: enable prefers-reduced-motion → no animations
7. **PatternGrid**: keyboard-only completion of pattern grid task
8. **Headings**: inspect heading hierarchy — no skips

---

## Files Summary

### Modified Files (systematic audit)
- `web/src/styles/base.css` — skip link styles, reduced motion media query
- `web/src/styles/tokens.css` — adjust muted text color if contrast fails
- `web/src/components/ui/Card.tsx` — role, tabIndex, onKeyDown for clickable
- `web/src/components/ui/Button.tsx` — verify aria attributes
- `web/src/components/ui/Badge.tsx` — aria-hidden for decorative
- `web/src/components/ui/Toggle.tsx` — verify label association
- `web/src/components/ui/TopBar.tsx` — aria-labels on buttons
- `web/src/components/ui/BottomNav.tsx` — role=tablist, tab roles, arrow keys
- `web/src/components/ui/ProgressBar.tsx` — role=progressbar, aria-value*
- `web/src/components/AppShell.tsx` — landmarks, skip link
- `web/src/components/PatternGrid.tsx` — role=grid, keyboard nav, reduced motion
- `web/src/components/SequenceOrder.tsx` — role=listbox/option, keyboard
- `web/src/components/KnowledgeGraph.tsx` — SVG keyboard nav
- `web/src/components/Chat.tsx` — aria-live, role=log
- `web/src/components/ScreeningResults.tsx` — semantic lists
- `web/src/components/onboarding/OnboardingFlow.tsx` — focus management, aria-labels
- All other view components — heading hierarchy, section labels
