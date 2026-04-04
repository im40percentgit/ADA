# Phase 13a — Design System + Responsive Layout + Companion Personalization

## Context

Ada has grown through 12 phases of feature development. The UI is functional but uses ad-hoc inline styles, no design system, a desktop-only sidebar layout, and hardcodes "Ada" as the companion name. For a wellness app serving patients with cognitive impairment, older adults, and anxious patients — plus their caregivers and clinicians — the UX needs to be warm, readable, mobile-first, and personalizable.

Phase 13a delivers a complete visual overhaul: design tokens, reusable components, responsive layout (mobile-first with bottom nav), dashboard and chat redesigns, companion personalization (name, voice, personality), and consistent restyling of all existing views.

## Design Direction: Warm & Human

**Aesthetic:** Empathetic, therapy-first, non-intimidating. Approachable for patients, trustworthy for clinicians.

**Color palette:**
- Surfaces: warm stone dark (#1c1917 base, #292524 card, #3b3634 elevated)
- Primary: purple (#7c3aed) with light (#a78bfa) and subtle (#2e1065)
- Semantic: green (#10b981 success), amber (#f59e0b warning), red (#ef4444 danger), soft pink (#fce7f3 warmth)
- Text: #fafaf9 (primary), #e7e5e4 (secondary), #a8a29e (muted)

**Typography:**
- Headings: Plus Jakarta Sans (bold, friendly geometric)
- Body: Nunito (round, approachable)
- Sizes: 24px h1, 18px h2, 16px body, 13px caption

**Spacing & Shape:**
- Base unit: 4px
- Card padding: 16px
- Card radius: 16px, button radius: 12px, input radius: 10px
- Section gap: 24px
- Touch target minimum: 44x44px

---

## 1. Design System Foundation

**Goal:** CSS custom properties defining every visual token so the entire app can be restyled by changing one file.

### `web/src/styles/tokens.css`

All design tokens as CSS custom properties on `:root`:
- `--color-bg-base`, `--color-bg-card`, `--color-bg-elevated`
- `--color-primary`, `--color-primary-light`, `--color-primary-subtle`
- `--color-success`, `--color-warning`, `--color-danger`, `--color-warmth`
- `--color-text-primary`, `--color-text-secondary`, `--color-text-muted`
- `--color-border`: #44403c
- `--font-heading`, `--font-body`
- `--size-h1` through `--size-caption`
- `--radius-card`, `--radius-button`, `--radius-input`
- `--space-xs` (4px) through `--space-2xl` (48px)
- `--shadow-card`, `--shadow-elevated`
- `--touch-target-min`: 44px

### `web/src/styles/base.css`

Global reset and base styles:
- Box-sizing border-box
- Body: font-family var(--font-body), background var(--color-bg-base), color var(--color-text-primary)
- Heading defaults using heading font
- Focus visible styles for accessibility

### `web/index.html`

Add Google Fonts links for Plus Jakarta Sans and Nunito. Import tokens.css and base.css.

---

## 2. Component Library

**Goal:** Reusable UI primitives that all views share. Each as a focused `.tsx` file.

### Components

**`Card.tsx`** — Rounded card with bg-card background, border, shadow. Props: `children`, `className`, `onClick` (makes it clickable with hover state). Used everywhere.

**`Button.tsx`** — Primary (purple bg), secondary (elevated bg), ghost (transparent). Props: `variant`, `size` (sm/md/lg), `disabled`, `onClick`, `children`. 44px min height on mobile.

**`Badge.tsx`** — Colored label chip. Props: `variant` (success/warning/danger/info/neutral), `children`. Used for severity labels, domain tags, status indicators.

**`Input.tsx`** — Styled text input with label, error state. Props: `label`, `error`, `type`, standard input props. 44px height.

**`Toggle.tsx`** — On/off switch for settings. Props: `checked`, `onChange`, `label`.

**`TopBar.tsx`** — App header: greeting on left, notification bell + avatar on right. Props: `greeting`, `subtitle`, `onNotification`, `onProfile`.

**`BottomNav.tsx`** — Fixed bottom tab bar with 4 tabs. Props: `activeTab`, `onTabChange`, `tabs: Array<{id, icon, label}>`. Highlights active tab with primary color.

**`ProgressBar.tsx`** — Horizontal progress indicator. Props: `value` (0-100), `color` (defaults to primary).

All components use CSS custom properties from tokens.css. No inline styles for colors/spacing — everything references tokens.

### File structure

```
web/src/components/ui/
  Card.tsx
  Button.tsx
  Badge.tsx
  Input.tsx
  Toggle.tsx
  TopBar.tsx
  BottomNav.tsx
  ProgressBar.tsx
```

---

## 3. Layout System

**Goal:** Mobile-first responsive app shell that works on 375px phones and 1440px desktops.

### `AppShell.tsx`

New layout component wrapping the entire app:

**Mobile (< 768px):**
- TopBar at top (greeting, notifications)
- Main content area (scrollable)
- BottomNav fixed at bottom (Home, Chat, Journey, Settings)
- No sidebar

**Desktop (≥ 768px):**
- Sidebar on left (vertical nav with icons + labels)
- TopBar at top of main content area
- Main content fills remaining space
- BottomNav hidden

Breakpoint: single `768px` breakpoint using `@media (min-width: 768px)`.

### Navigation mapping

| Tab | Mobile Icon | Desktop Label | View |
|-----|-------------|---------------|------|
| Home | 🏠 | Dashboard | PatientDashboard / CaregiverDashboard |
| Chat | 💬 | Talk to {name} | Chat view |
| Journey | 🗺️ | My Journey | KnowledgeGraph |
| Settings | ⚙️ | Settings | SettingsPage (new) |

Sub-views (ProgressReport, SessionSummary, ScreeningResults, etc.) render in the main content area with a back button — they don't change the nav tab.

### App.tsx refactor

Replace current sidebar/view logic with `<AppShell>`. The `View` type and state management stay, but rendering delegates to AppShell for layout.

---

## 4. Patient Dashboard Redesign

**Goal:** Card-based mobile-first layout replacing the current flat section layout.

### Layout

- Personalized greeting in TopBar ("Good morning, Sarah")
- Hero card: "Talk to {companionName}" with purple gradient, "Start Session" button
- Wellbeing score card: WHO-5 score (large), sparkline, delta, severity label
- 2x2 quick action grid: Medications (count), Appointments (next), Screening (score), Progress (link)
- Recent sessions card: last 3 sessions, clickable
- Alerts card: active crisis alerts (if any), prominent

All cards use the `<Card>` component. Grid uses CSS Grid with `repeat(2, 1fr)` on mobile, `repeat(4, 1fr)` on desktop.

### Data

Same data as current PatientDashboard — no API changes needed. Just restyled rendering.

---

## 5. Caregiver Dashboard Redesign

**Goal:** Same design system applied to the caregiver view.

- TopBar with caregiver name
- Patient selector (if caregiver has multiple circles)
- Alert cards prominent (crisis alerts at top)
- Patient overview: wellbeing score, last session, medication adherence
- Quick actions: Knowledge Map, Progress Report, Screening History
- Daily summary preview card
- Grid layout matching patient dashboard pattern

---

## 6. Chat Redesign

**Goal:** Warm, rounded chat bubbles with companion personalization.

- Chat header: companion name (not hardcoded "Ada"), online status dot
- User messages: right-aligned, primary-subtle background
- Companion messages: left-aligned, card background, rounded with tail
- Typing indicator: animated dots in companion bubble style
- Voice mode button: prominent, uses primary color
- Media controls: styled with tokens, rounded
- Cognitive task cards: embedded in chat with card styling
- Crisis alerts: danger-colored card with prominent styling
- Emotion chip: uses badge component

All existing functionality preserved — just restyled with tokens and components.

---

## 7. Companion Personalization

**Goal:** Users choose their companion's name, voice, and personality.

### Database

New table:
```sql
CREATE TABLE IF NOT EXISTS companion_preferences (
    user_id     TEXT PRIMARY KEY REFERENCES users(id),
    name        TEXT NOT NULL DEFAULT 'Ada',
    voice       TEXT NOT NULL DEFAULT 'female' CHECK(voice IN ('male', 'female', 'neutral')),
    personality TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

`personality` JSON structure:
```json
{
  "warmth": "warm",         // warm | professional
  "verbosity": "balanced",  // chatty | balanced | concise
  "formality": "casual"     // casual | balanced | formal
}
```

### API

- `GET /api/companion/preferences` — returns current user's companion preferences (defaults if none)
- `PUT /api/companion/preferences` — update preferences `{ name, voice, personality }`

### System Prompt Injection

Modify `WellnessCompanionAgent` (and any agent that talks to patients) to prepend personality traits to the system prompt:

```
Your name is {name}. You are a wellness companion.
Communication style: {warmth}, {verbosity}, {formality}.
```

This is injected via the agent's `_build_system_prompt()` method, reading preferences from state for the current patient's user.

### TTS Voice Selection

Map voice preference to Piper voice models:
- `female` → current default Piper voice
- `male` → male Piper voice model
- `neutral` → neutral/androgynous voice if available, else female

The TTSAgent reads the user's voice preference when generating speech.

### Settings Page

New `web/src/components/SettingsPage.tsx`:
- Companion name: text input with preview ("Your companion: {name}")
- Voice: radio buttons (Female / Male / Neutral) with audio preview button
- Personality: three slider/toggle rows:
  - Warmth: Warm ←→ Professional
  - Verbosity: Chatty ←→ Concise
  - Formality: Casual ←→ Formal
- Save button
- Account section: email, change password link, logout

### UI Integration

Throughout the app, replace hardcoded "Ada" with the user's companion name:
- Chat header
- "Talk to Ada" → "Talk to {name}"
- Dashboard greeting
- Assessment prompts
- Notification text

Use a `useCompanionPreferences` hook that fetches once and caches.

---

## 8. Remaining Views Restyle

**Goal:** Apply the design system consistently to all existing views.

### Views to restyle

Each view gets tokens + Card/Badge/Button components:

- **KnowledgeGraph** — filters use Badge for chips, Card for detail panel, Button for controls
- **ProgressReport** — Card for chart sections, narrative card uses warmth tint, Badge for severity
- **SessionSummary** — Card for each SOAP section, Badge for risk flags
- **DailySummaryDetail** — Card for narrative, trend alert cards
- **ScreeningResults** — Card for domain section, Badge for scores
- **CognitiveScreening** — Card for task area, ProgressBar for progress
- **Login/ForgotPassword/ResetPassword** — centered card layout, Input components, Button
- **AssessmentForm** — Card for question groups, Button for scale options
- **NotificationPreferences** — Toggle components for each setting

### Approach

For each view: replace inline styles with token references, wrap sections in `<Card>`, use `<Badge>` for labels, use `<Button>` for actions, ensure 44px touch targets, verify responsive at 375px.

---

## Verification Plan

1. **Design tokens**: inspect computed styles — all colors/spacing match token values
2. **Responsive**: resize browser to 375px — bottom nav visible, cards stack, no horizontal scroll
3. **Desktop**: resize to 1440px — sidebar visible, grid expands
4. **Chat**: send messages — bubbles styled warmly, companion name shown
5. **Personalization**: change name in settings → reflected in chat header, dashboard, notifications
6. **Voice**: change voice preference → TTS uses correct voice model
7. **Personality**: change personality → next chat message reflects the style change
8. **Touch targets**: on mobile — all buttons/inputs are at least 44x44px
9. **All views**: navigate through every view — consistent styling, no unstyled sections

---

## Files Summary

### New Files
- `web/src/styles/tokens.css`
- `web/src/styles/base.css`
- `web/src/components/ui/Card.tsx`
- `web/src/components/ui/Button.tsx`
- `web/src/components/ui/Badge.tsx`
- `web/src/components/ui/Input.tsx`
- `web/src/components/ui/Toggle.tsx`
- `web/src/components/ui/TopBar.tsx`
- `web/src/components/ui/BottomNav.tsx`
- `web/src/components/ui/ProgressBar.tsx`
- `web/src/components/AppShell.tsx`
- `web/src/components/SettingsPage.tsx`
- `web/src/hooks/useCompanionPreferences.ts`
- `ada/api/routes/companion.py`
- `tests/unit/test_companion_preferences.py`
- Component test files for UI primitives

### Modified Files
- `web/index.html` — fonts, CSS imports
- `web/src/App.tsx` — AppShell layout, Settings view
- `web/src/App.css` — major overhaul (or replaced by component-scoped styles)
- Every existing component — restyled with tokens and UI components
- `ada/core/state.py` — companion_preferences table
- `ada/api/app.py` — register companion router
- `ada/agents/wellness_companion.py` — personality injection
- `ada/agents/tts.py` — voice preference
- `config/default.toml` — default companion settings
