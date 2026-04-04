# Phase 13a — Design System + Responsive Layout + Companion Personalization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Ada from a prototype with ad-hoc styling into a polished, mobile-first wellness app with a cohesive design system, responsive layout, and companion personalization (name, voice, personality).

**Architecture:** CSS custom properties define all visual tokens. A small component library (Card, Button, Badge, etc.) consumes these tokens. An AppShell layout component handles responsive behavior (bottom nav on mobile, sidebar on desktop). All existing views are restyled to use the new system. Companion preferences are stored server-side and injected into LLM prompts and TTS voice selection.

**Tech Stack:** CSS Custom Properties (tokens), React/TypeScript (components), Plus Jakarta Sans + Nunito (fonts), Python/FastAPI (companion API), aiosqlite (preferences storage)

**Design Spec:** `docs/superpowers/specs/2026-04-04-phase13a-design-system-responsive-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `web/src/styles/tokens.css` | All design tokens as CSS custom properties |
| `web/src/styles/base.css` | Reset, typography defaults, focus styles |
| `web/src/components/ui/Card.tsx` | Rounded card container |
| `web/src/components/ui/Button.tsx` | Primary/secondary/ghost button variants |
| `web/src/components/ui/Badge.tsx` | Colored label chip |
| `web/src/components/ui/Input.tsx` | Styled text input with label/error |
| `web/src/components/ui/Toggle.tsx` | On/off switch |
| `web/src/components/ui/TopBar.tsx` | App header with greeting + actions |
| `web/src/components/ui/BottomNav.tsx` | Fixed bottom tab navigation |
| `web/src/components/ui/ProgressBar.tsx` | Horizontal progress indicator |
| `web/src/components/AppShell.tsx` | Responsive layout (mobile bottom nav / desktop sidebar) |
| `web/src/components/SettingsPage.tsx` | Companion + account settings |
| `web/src/hooks/useCompanionPreferences.ts` | Fetch/cache companion preferences |
| `ada/api/routes/companion.py` | Companion preferences CRUD endpoints |
| `tests/unit/test_companion_preferences.py` | Backend tests |
| `web/test/components/ui/Card.test.tsx` | Component tests |
| `web/test/components/ui/Button.test.tsx` | Component tests |
| `web/test/components/AppShell.test.tsx` | Layout tests |
| `web/test/components/SettingsPage.test.tsx` | Settings tests |

### Modified Files

| File | Changes |
|------|---------|
| `web/index.html` | Google Fonts links, CSS imports |
| `web/src/App.tsx` | Replace sidebar with AppShell, add Settings view |
| `web/src/App.css` | Major overhaul — replace with token-based styles |
| `ada/core/state.py` | Add companion_preferences table + CRUD |
| `ada/api/app.py` | Register companion router |
| `ada/agents/wellness_companion.py` | Personality injection in system prompt |
| `ada/agents/tts.py` | Voice preference mapping |
| `config/default.toml` | Default companion settings |
| `ada/core/config.py` | CompanionConfig model |
| All dashboard/view components | Restyle with tokens + UI components |

---

## Task 1: Design Tokens + Base Styles

**Files:**
- Create: `web/src/styles/tokens.css`
- Create: `web/src/styles/base.css`
- Modify: `web/index.html`

- [ ] Create `web/src/styles/tokens.css` with all CSS custom properties on `:root`. Include: surface colors (bg-base #1c1917, bg-card #292524, bg-elevated #3b3634), primary palette (primary #7c3aed, primary-light #a78bfa, primary-subtle #2e1065), semantic colors (success #10b981, warning #f59e0b, danger #ef4444, warmth #fce7f3), text colors (text-primary #fafaf9, text-secondary #e7e5e4, text-muted #a8a29e), border (#44403c), font families (font-heading 'Plus Jakarta Sans', font-body 'Nunito'), sizes (h1 24px, h2 18px, body 16px, sm 14px, caption 13px, xs 11px), radii (card 16px, button 12px, input 10px), spacing (xs 4px, sm 8px, md 16px, lg 24px, xl 32px, 2xl 48px), shadows, touch-target-min 44px.
- [ ] Create `web/src/styles/base.css`: box-sizing reset, body using tokens (font-body, bg-base, text-primary), heading defaults (font-heading, appropriate sizes), link defaults, focus-visible outline (2px solid primary, 2px offset), smooth scrolling.
- [ ] Modify `web/index.html`: add Google Fonts `<link>` for Plus Jakarta Sans (weights 500,600,700) and Nunito (weights 400,600,700). Add `<link rel="stylesheet" href="/src/styles/tokens.css">` and `<link rel="stylesheet" href="/src/styles/base.css">` (or import in main.tsx).
- [ ] Verify: open the app — fonts load, background color changes to warm stone.
- [ ] Commit: `feat(phase13a): add design tokens and base styles with warm human palette`

---

## Task 2: UI Component Library

**Files:**
- Create: `web/src/components/ui/Card.tsx`
- Create: `web/src/components/ui/Button.tsx`
- Create: `web/src/components/ui/Badge.tsx`
- Create: `web/src/components/ui/Input.tsx`
- Create: `web/src/components/ui/Toggle.tsx`
- Create: `web/src/components/ui/ProgressBar.tsx`
- Create: `web/test/components/ui/Card.test.tsx`
- Create: `web/test/components/ui/Button.test.tsx`

- [ ] Create `Card.tsx`: renders `<div>` with className `ada-card` + optional `ada-card--clickable` when onClick is provided. Styles: background var(--color-bg-card), border 1px solid var(--color-border), border-radius var(--radius-card), padding var(--space-md), box-shadow var(--shadow-card). Clickable variant adds hover brightness and cursor pointer. Props: `{ children, className?, onClick?, style? }`.
- [ ] Create `Button.tsx`: three variants. `primary`: bg primary, white text. `secondary`: bg elevated, text-primary. `ghost`: transparent bg, text-muted. All: border-radius var(--radius-button), min-height var(--touch-target-min), padding 0 var(--space-md), font-family var(--font-body), font-weight 600. Disabled state: opacity 0.5. Props: `{ variant?, size?, disabled?, onClick?, children, className?, type? }`.
- [ ] Create `Badge.tsx`: inline-flex span. Variants map to colors: success (green bg/text), warning (amber), danger (red), info (primary), neutral (muted). Styles: padding 2px 8px, border-radius 10px, font-size var(--size-xs), font-weight 600. Props: `{ variant, children, className? }`.
- [ ] Create `Input.tsx`: `<label>` wrapper with `<input>` inside. Label uses caption size, muted color. Input: bg bg-elevated, border, radius input, height touch-target-min, padding, font-body. Error state: red border, error message below. Props: `{ label?, error?, ...InputHTMLAttributes }`.
- [ ] Create `Toggle.tsx`: checkbox styled as switch. Track: 44x24px, bg-elevated. Thumb: 20x20px circle, transitions left. Checked: track bg primary, thumb slides right. Props: `{ checked, onChange, label?, disabled? }`.
- [ ] Create `ProgressBar.tsx`: outer div (bg-elevated, height 6px, border-radius 3px). Inner div (width from value prop, bg primary or custom color, border-radius 3px, transition width). Props: `{ value: number, color?, className? }`.
- [ ] Write tests: `Card.test.tsx` (renders children, clickable adds class, onClick fires), `Button.test.tsx` (renders variants, disabled state, onClick fires).
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase13a): add UI component library (Card, Button, Badge, Input, Toggle, ProgressBar)`

---

## Task 3: AppShell + Responsive Layout

**Files:**
- Create: `web/src/components/ui/TopBar.tsx`
- Create: `web/src/components/ui/BottomNav.tsx`
- Create: `web/src/components/AppShell.tsx`
- Create: `web/test/components/AppShell.test.tsx`
- Modify: `web/src/App.tsx`

- [ ] Create `TopBar.tsx`: flex row with greeting (left) and action buttons (right). Left: subtitle (caption, muted) + title (h2 size, bold). Right: notification bell button + avatar circle. Props: `{ greeting, subtitle?, onNotification?, onProfile?, notificationCount? }`.
- [ ] Create `BottomNav.tsx`: fixed bottom bar. Background bg-card, border-top. Flex row of tab items, each with icon + label. Active tab: primary color. Inactive: text-muted. 44px min height per tab. Props: `{ tabs: Array<{id, icon, label}>, activeTab, onTabChange }`.
- [ ] Create `AppShell.tsx`: responsive wrapper.
  - Mobile (< 768px): TopBar at top, scrollable main content (`children`), BottomNav at bottom. Main content has padding-bottom for nav height.
  - Desktop (≥ 768px): sidebar left (vertical nav, 240px wide, bg-card), TopBar at top of main area, main content fills rest. BottomNav hidden.
  - Uses CSS `@media (min-width: 768px)` for breakpoint.
  - Props: `{ children, activeTab, onTabChange, greeting, subtitle?, companionName?, onNotification? }`.
- [ ] Modify `App.tsx`: replace current sidebar/nav logic with `<AppShell>`. Map the View state to tabs. Keep all existing view rendering logic inside AppShell's children area. Add 'settings' to the View type.
- [ ] Write `AppShell.test.tsx`: renders children, renders TopBar, renders BottomNav (mock matchMedia for mobile), tab change fires callback.
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase13a): add AppShell responsive layout with bottom nav and sidebar`

---

## Task 4: Companion Preferences Backend

**Files:**
- Create: `ada/api/routes/companion.py`
- Create: `tests/unit/test_companion_preferences.py`
- Modify: `ada/core/state.py`
- Modify: `ada/core/config.py`
- Modify: `config/default.toml`
- Modify: `ada/api/app.py`

- [ ] Add `companion_preferences` table to `_SCHEMA` in `ada/core/state.py`: user_id (PK, FK users), name (default 'Ada'), voice (CHECK male/female/neutral, default 'female'), personality (JSON, default '{}'), updated_at.
- [ ] Add CRUD: `get_companion_preferences(user_id) -> dict | None`, `set_companion_preferences(user_id, prefs) -> None` (INSERT OR REPLACE).
- [ ] Add config: `[companion]` section in `default.toml` with `default_name = "Ada"`, `default_voice = "female"`. Add `CompanionConfig` to `ada/core/config.py`.
- [ ] Create `ada/api/routes/companion.py`: `GET /api/companion/preferences` (returns current user's prefs with defaults for missing fields), `PUT /api/companion/preferences` (accepts partial update, upserts).
- [ ] Register router in `ada/api/app.py`.
- [ ] Write `tests/unit/test_companion_preferences.py`: test defaults, set/get, partial update, voice constraint.
- [ ] Run: `python3 -m pytest tests/unit/test_companion_preferences.py -v` — all pass.
- [ ] Commit: `feat(phase13a): add companion preferences backend (name, voice, personality)`

---

## Task 5: Companion Personalization Integration

**Files:**
- Modify: `ada/agents/wellness_companion.py`
- Modify: `ada/agents/tts.py` (or `ada/agents/tts_agent.py`)
- Create: `web/src/hooks/useCompanionPreferences.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/types/index.ts`

- [ ] Add TypeScript types: `CompanionPreferences { name: string; voice: 'male'|'female'|'neutral'; personality: { warmth: string; verbosity: string; formality: string } }`.
- [ ] Add API functions: `getCompanionPreferences(): Promise<CompanionPreferences>`, `updateCompanionPreferences(prefs: Partial<CompanionPreferences>): Promise<CompanionPreferences>`.
- [ ] Create `useCompanionPreferences.ts`: fetches on mount, caches in state. Returns `{ preferences, loading, update }`. The `update` function calls the API and refreshes local state.
- [ ] Modify `wellness_companion.py`: in the system prompt builder, read companion preferences for the current patient's user. Prepend personality traits: `"Your name is {name}. Communication style: {warmth}, {verbosity}, {formality}."` Read preferences via `self.state.get_companion_preferences(user_id)`.
- [ ] Modify TTS agent: read voice preference. Map to Piper voice model selection. Read existing TTS code first to understand how voice model is selected.
- [ ] Add MSW handler and factory for companion preferences endpoint.
- [ ] Commit: `feat(phase13a): integrate companion personalization into agents and frontend`

---

## Task 6: Settings Page

**Files:**
- Create: `web/src/components/SettingsPage.tsx`
- Create: `web/test/components/SettingsPage.test.tsx`

- [ ] Create `SettingsPage.tsx` using Card, Input, Button, Toggle components:
  - **Companion section**: Card with name Input ("What would you like to call your companion?"), voice radio buttons (Female/Male/Neutral) using styled radio inputs, personality controls (3 rows, each a label + toggle between two options: Warm↔Professional, Chatty↔Concise, Casual↔Formal).
  - **Account section**: Card showing email (read-only), "Change Password" link (navigates to forgot-password flow), Logout button (danger variant).
  - Save button at bottom for companion changes.
  - Uses `useCompanionPreferences` hook for data.
  - Props: `{ onLogout: () => void; onNavigate: (view: string) => void }`.
- [ ] Write tests: renders companion name input, renders voice options, save calls update API, logout button fires callback.
- [ ] Run: `cd web && npx vitest run` — all pass.
- [ ] Commit: `feat(phase13a): add settings page with companion personalization and account controls`

---

## Task 7: Dashboard Redesigns

**Files:**
- Modify: `web/src/components/PatientDashboard.tsx`
- Modify: `web/src/components/CaregiverDashboard.tsx`

- [ ] Redesign `PatientDashboard.tsx`:
  - Replace all inline styles and flat sections with Card components + token-based styles
  - Add hero "Talk to {companionName}" card at top with gradient background (linear-gradient using primary colors)
  - Wellbeing score Card: large score, sparkline (existing MoodChart data), delta, severity Badge
  - 2x2 grid of quick action Cards: Medications (with count Badge), Appointments (next date), Screening (score Badge), Progress (link)
  - Use `useCompanionPreferences` to get companion name for the hero card
  - All cards 44px min touch targets, responsive grid (2 cols mobile, 4 cols desktop)
- [ ] Redesign `CaregiverDashboard.tsx`:
  - Same token/Card treatment
  - Alert Cards at top (if any crisis alerts — danger Badge)
  - Patient overview Card (wellbeing score, last session, adherence)
  - Quick action grid: Knowledge Map, Progress, Screening History
  - Daily summary preview Card
- [ ] Run: `cd web && npx vitest run` — all existing dashboard tests pass (may need test updates if selectors changed).
- [ ] Commit: `feat(phase13a): redesign patient and caregiver dashboards with design system`

---

## Task 8: Chat + Remaining Views Restyle

**Files:**
- Modify: `web/src/components/Chat.tsx`
- Modify: All remaining view components (KnowledgeGraph, ProgressReport, SessionSummary, DailySummaryDetail, ScreeningResults, CognitiveScreening, Login, ForgotPassword, ResetPassword, AssessmentForm, NotificationPreferences, etc.)

- [ ] Redesign `Chat.tsx`:
  - Chat header: show companion name (from useCompanionPreferences), online status dot
  - User messages: right-aligned, primary-subtle background, rounded with card radius
  - Companion messages: left-aligned, card background, rounded
  - Voice mode button: primary color, rounded, prominent
  - All interactive elements: 44px touch targets
  - Cognitive task cards: use Card component
  - Emotion chip: use Badge component
- [ ] Restyle remaining views (batch approach — each view gets):
  - Replace inline styles with token CSS variables
  - Wrap sections in Card components
  - Use Badge for labels/tags/severity
  - Use Button for all actions
  - Use Input for all form fields
  - Ensure responsive at 375px (stack cards vertically)
  - Apply to: KnowledgeGraph (filters → Badge chips), ProgressReport (chart Cards), SessionSummary (SOAP Cards), DailySummaryDetail, ScreeningResults (domain Cards), CognitiveScreening (task Card), Login/Register (centered Card), ForgotPassword/ResetPassword (centered Card), AssessmentForm (question Cards), NotificationPreferences (Toggle components), PatternGrid/SequenceOrder/ClockTask (Card wrappers)
- [ ] Run: `cd web && npx vitest run` — all tests pass (update test selectors as needed).
- [ ] Commit: `feat(phase13a): restyle chat and all remaining views with design system`

---

## Verification Checklist

- [ ] All design tokens applied: inspect computed styles — colors match palette
- [ ] Mobile (375px): bottom nav visible, cards stack, no horizontal scroll, 44px touch targets
- [ ] Desktop (1440px): sidebar visible, grid expands, no bottom nav
- [ ] Chat: companion name shown (not hardcoded "Ada"), warm bubble styling
- [ ] Settings: can change companion name, voice, personality → reflected in chat
- [ ] All views: consistent Card/Badge/Button usage, no unstyled sections
- [ ] Backend: `python3 -m pytest tests/unit/test_companion_preferences.py -v` — all pass
- [ ] Frontend: `cd web && npx vitest run` — all pass
