# Phase 13c — Accessibility (WCAG 2.1 AA) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ada WCAG 2.1 AA compliant: keyboard navigable, screen reader compatible, proper contrast, semantic HTML, focus management, and motion control.

**Architecture:** Systematic audit-and-fix across all components. No new features — only ARIA attributes, keyboard handlers, semantic elements, focus management, and CSS adjustments. Split into three tasks: UI primitives + base styles, interactive components (visual tasks + graph), and all view components.

**Tech Stack:** ARIA attributes, semantic HTML, CSS (focus, skip link, reduced motion), keyboard event handlers

**Design Spec:** `docs/superpowers/specs/2026-04-04-phase13c-accessibility-design.md`

---

## Task 1: Base Styles + UI Primitives Accessibility

**Files to modify:**
- `web/src/styles/base.css` — skip link, reduced motion
- `web/src/styles/tokens.css` — contrast adjustment if needed
- `web/src/components/ui/Card.tsx` — role, tabIndex, keyboard handler
- `web/src/components/ui/Button.tsx` — aria attributes
- `web/src/components/ui/Badge.tsx` — aria-hidden for decorative
- `web/src/components/ui/Toggle.tsx` — label association
- `web/src/components/ui/TopBar.tsx` — aria-labels
- `web/src/components/ui/BottomNav.tsx` — tablist role, arrow keys
- `web/src/components/ui/ProgressBar.tsx` — progressbar role
- `web/src/components/AppShell.tsx` — landmarks, skip link

- [ ] Add to `base.css`: `.skip-link` styles (visually hidden, visible on `:focus`, position absolute top). Add `@media (prefers-reduced-motion: reduce)` disabling animations/transitions globally.
- [ ] Verify contrast: check `--color-text-muted` on `--color-bg-card`. If below 4.5:1, lighten to #b8b2ae or similar.
- [ ] `Card.tsx`: when `onClick` provided, add `role="button"`, `tabIndex={0}`, `onKeyDown` handler for Enter/Space.
- [ ] `Badge.tsx`: add `aria-hidden="true"` when purely decorative (no prop change needed — decorative use is implicit when Badge is adjacent to visible text).
- [ ] `TopBar.tsx`: `aria-label="Notifications"` on bell button, `aria-label="Profile menu"` on avatar.
- [ ] `BottomNav.tsx`: `<nav aria-label="Main navigation">`, `role="tablist"` on tab container, each tab `role="tab"`, `aria-selected`, add `onKeyDown` for arrow key navigation between tabs.
- [ ] `ProgressBar.tsx`: `role="progressbar"`, `aria-valuenow={value}`, `aria-valuemin={0}`, `aria-valuemax={100}`, `aria-label` prop.
- [ ] `Toggle.tsx`: verify hidden checkbox has associated label text (via aria-label or visible label).
- [ ] `AppShell.tsx`: wrap TopBar area in `<header>`, nav in `<nav>`, content in `<main id="main-content">`. Add skip link as first child: `<a href="#main-content" className="skip-link">Skip to main content</a>`.
- [ ] Run: `cd web && npx vitest run` — all pass (update tests if role/aria changes break queries).
- [ ] Commit: `feat(phase13c): add accessibility to base styles and UI primitives (WCAG 2.1 AA)`

---

## Task 2: Interactive Components Accessibility

**Files to modify:**
- `web/src/components/PatternGrid.tsx` — grid role, keyboard nav, reduced motion
- `web/src/components/SequenceOrder.tsx` — listbox role, keyboard
- `web/src/components/ClockTask.tsx` — verify button a11y
- `web/src/components/KnowledgeGraph.tsx` — SVG keyboard nav
- `web/src/components/GraphDetailPanel.tsx` — focus trap, escape
- `web/src/components/Chat.tsx` — aria-live, role=log
- `web/src/components/ConnectionStatus.tsx` — role=status, aria-live
- `web/src/components/onboarding/OnboardingFlow.tsx` — focus management

- [ ] `PatternGrid.tsx`: add `role="grid"` on container, `role="gridcell"` on cells, `tabIndex={0}` on cells during recall phase, `onKeyDown` for Enter/Space to toggle, arrow keys to navigate grid, `aria-label="Cell {n}, {selected|unselected}"`. For `prefers-reduced-motion`: keep pattern visible until user clicks "I'm ready" button instead of auto-hiding.
- [ ] `SequenceOrder.tsx`: available items area `role="listbox"`, items `role="option"`, `tabIndex={0}`, Enter/Space to select. Answer area shows ordered items. Arrow keys to navigate within each list.
- [ ] `ClockTask.tsx`: options are already buttons — add `aria-pressed` on selected, `aria-label` on SVG clock with time description.
- [ ] `KnowledgeGraph.tsx`: add `<title>` and `<desc>` to SVG for screen readers. Node groups `<g>` get `tabIndex={0}`, `role="button"`, `aria-label="{label} node, {mention_count} mentions"`. Enter to select node. Escape to close detail panel.
- [ ] `GraphDetailPanel.tsx`: `role="dialog"`, `aria-labelledby` pointing to heading, `aria-modal="true"`. Focus trap: on mount, focus first element; Tab cycles within panel. Escape handler to close. On close, return focus to the node that opened it.
- [ ] `Chat.tsx`: message list container `role="log"`, `aria-live="polite"`, `aria-label="Chat messages"`. Each message `role="listitem"` if using a list. New message area: `aria-label="Message input"`.
- [ ] `ConnectionStatus.tsx`: `role="status"`, `aria-live="polite"`.
- [ ] `OnboardingFlow.tsx`: on step change, focus the step heading. `aria-label="Onboarding step {n} of 7"` on the step container.
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase13c): add keyboard navigation and ARIA to interactive components`

---

## Task 3: View Components Semantic HTML + A11y

**Files to modify:**
- `web/src/components/PatientDashboard.tsx`
- `web/src/components/CaregiverDashboard.tsx`
- `web/src/components/ProgressReport.tsx`
- `web/src/components/SessionSummary.tsx`
- `web/src/components/DailySummaryDetail.tsx`
- `web/src/components/ScreeningResults.tsx`
- `web/src/components/CognitiveScreening.tsx`
- `web/src/components/ScreeningHistory.tsx`
- `web/src/components/ClinicianNotes.tsx`
- `web/src/components/Login.tsx`
- `web/src/components/ForgotPassword.tsx`
- `web/src/components/ResetPassword.tsx`
- `web/src/components/SettingsPage.tsx`
- `web/src/components/NotificationPreferences.tsx`

- [ ] **Dashboards**: wrap card sections in `<section aria-label="Wellbeing score">`, etc. Ensure heading hierarchy (h1 for page title, h2 for sections). Alert cards: `role="alert"` for crisis alerts.
- [ ] **ProgressReport**: section labels, chart aria-labels ("WHO-5 Wellbeing Trend chart"), assessment scores aria-labels.
- [ ] **SessionSummary**: SOAP sections as `<section>` with h2 headings. Risk flags with `role="alert"` for HIGH/CRITICAL.
- [ ] **DailySummaryDetail**: sections with headings, trend alerts as `<ul>`.
- [ ] **ScreeningResults**: domain bars with aria-labels, task breakdown as `<ol>`.
- [ ] **CognitiveScreening**: step content in `<section>`, progress with aria-live.
- [ ] **ScreeningHistory**: timeline as `<ol>`, each entry `<li>` with aria-label.
- [ ] **ClinicianNotes**: textarea `aria-label="Add clinical note"`, notes list as `<ul>`.
- [ ] **Auth forms**: `<form>` elements, inputs with `<label>`, submit buttons properly typed, error messages with `aria-describedby` linking input to error.
- [ ] **SettingsPage**: `<form>` wrapper, fieldset for companion settings, legend for sections.
- [ ] **NotificationPreferences**: toggle labels properly associated.
- [ ] Verify heading hierarchy across all views — no skipped levels.
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase13c): add semantic HTML and ARIA labels to all view components`

---

## Verification Checklist

- [ ] Tab through entire app without mouse — every element reachable
- [ ] Skip link visible on first Tab, jumps to main content
- [ ] PatternGrid: complete task using only keyboard
- [ ] SequenceOrder: order items using only keyboard
- [ ] GraphDetailPanel: focus trapped, Escape closes, focus returns
- [ ] Screen reader: all elements have meaningful announcements
- [ ] Muted text on card background meets 4.5:1 contrast
- [ ] Reduced motion: enable preference → no animations
- [ ] All tests pass: `cd web && npx vitest run`
