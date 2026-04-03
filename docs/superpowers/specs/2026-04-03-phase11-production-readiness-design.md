# Phase 11 — Production Readiness

## Context

Ada has 10 phases of features: conversational therapy, auth, agent orchestration, multimodal sensing, caregiver dashboards, care circles, shared boards, push notifications, and patient/caregiver product loops. The backend is comprehensive (16 agents, 27 tables, 60+ endpoints, 939 tests) but the frontend has zero test coverage, WebSocket connections fail silently, agent errors are invisible to users, there's no account recovery flow, notifications lack user preferences, and the app is only accessible on localhost. Phase 11 makes Ada shippable.

## Structure

**Phase 11a — Foundation (Testing + Resilience):** Build the infrastructure that all future work depends on.
**Phase 11b — Features (Account Recovery + Notification Polish + PWA):** Ship user-facing features with tests from day one.

---

## Phase 11a — Foundation

### 1. Frontend Testing Infrastructure

**Goal:** Establish Vitest + React Testing Library + MSW so every component has a testable harness.

**Setup files:**
- `web/vitest.config.ts` — Vitest config with jsdom environment, path aliases matching `vite.config.ts`
- `web/test/setup.ts` — RTL cleanup, MSW server start/stop, global mocks for `localStorage` and `WebSocket`
- `web/test/msw/handlers.ts` — MSW request handlers mirroring real API responses
- `web/test/factories.ts` — Test data factories for User, Patient, Session, Message, Medication, Appointment, Circle, Board

**Component tests (priority order):**

| Component | What to test | Why critical |
|-----------|-------------|--------------|
| `Login.tsx` | Register flow, login flow, validation errors, token storage | Auth gate for entire app |
| `Chat.tsx` | Send message, receive streamed response, display crisis alert | Core product experience |
| `PatientDashboard.tsx` | Renders all 6 cards, medication logging, alert resolution | Patient's primary view |
| `CaregiverDashboard.tsx` | Loads overview data, displays patient status, alert list | Caregiver's primary view |
| `BoardView.tsx` | Add item, edit item, approve suggestion, real-time update | Collaboration feature |
| `NotificationBell.tsx` | Permission request, subscribe/unsubscribe, visual states | Just-merged feature, untested |

**Dependencies:** `vitest`, `@testing-library/react`, `@testing-library/user-event`, `jsdom`, `msw`

**Test count target:** ~40-50 component tests across the 6 components.

### 2. WebSocket Resilience

**Goal:** WebSocket connections auto-reconnect with user-visible status. Messages sent during disconnect are queued and delivered on reconnect.

#### `useReconnectingWebSocket` hook

Wraps the existing `useWebSocket` hook. New file: `web/src/hooks/useReconnectingWebSocket.ts`

**State machine:**
```
CONNECTED ──onclose──→ RECONNECTING ──max retries──→ DISCONNECTED
    ↑                       │                              │
    └───────onopen──────────┘         manual retry ────────┘
```

**Configuration:**
- `initialDelay`: 1000ms
- `maxDelay`: 30000ms
- `backoffMultiplier`: 2
- `maxRetries`: 10
- `jitter`: true (±20% randomization to prevent thundering herd)

**Message queue:** Messages sent while disconnected are stored in a bounded queue (max 50 messages). On reconnect, queued messages are flushed in order before new sends are allowed. Queue overflow drops oldest messages.

**Returns:**
```typescript
{
  status: 'connected' | 'reconnecting' | 'disconnected'
  retryCount: number
  send: (msg: string) => void    // queues if disconnected
  retry: () => void              // manual reconnect
  lastMessage: MessageEvent | null
}
```

**Integration:** `useChat` and `useBoardWebSocket` switch from `useWebSocket` to `useReconnectingWebSocket`. Existing API unchanged — `send` and `lastMessage` work identically.

#### `ConnectionStatus` component

New file: `web/src/components/ConnectionStatus.tsx`

Renders a top-of-page banner based on WebSocket status:
- **Connected:** Brief green "Reconnected" banner, auto-hides after 2 seconds. Hidden on initial connect.
- **Reconnecting:** Amber banner: "Reconnecting... (attempt 3/10)". Non-blocking, no user action needed.
- **Disconnected:** Red banner: "Connection lost" with a "Retry" button. Persistent until user clicks retry or connection restores.

Mounted in `App.tsx` above the main content area. Receives status from the chat WebSocket (primary connection indicator).

### 3. Agent Failure Handling

**Goal:** When an agent's LLM call fails or times out, the user gets a graceful fallback instead of silence.

#### Backend: `AgentErrorHandler`

New file: `ada/agents/error_handler.py`

**Timeout wrapper:**
```python
async def with_timeout(coro, timeout_seconds=30, fallback=None):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return fallback
```

Applied in `BaseAgent.handle_event` around every `llm_provider.generate()` call. Timeout configurable per-agent in `config/default.toml` under `[agents.<name>]`.

**Fallback responses by agent type:**
- `WellnessCompanionAgent`: Returns a friendly message: "I'm having a moment — could you try saying that again?" Maintains conversation continuity.
- `CrisisMonitorAgent`: **Always escalates on error.** Publishes a HIGH severity crisis alert. Fail-safe, never fail-silent.
- `EmotionAnalyzerAgent`, `VoiceEmotionAgent`, `FacialEmotionAgent`, `PhysiologicalAgent`: Silent failure. These are background enrichment — no user-facing impact.
- `MultimodalFusionAgent`: Skips fusion cycle. Next incoming signal retriggers.
- `KnowledgeAgent`: Returns empty consultation response. TherapistAgent proceeds without context enrichment (existing 2s timeout behavior, now formalized).
- `SessionSummarizerAgent`, `DailySummaryGeneratorAgent`, `BoardSuggestionAgent`: Log error, skip this cycle. Next trigger retries.

**Circuit breaker:**
New file: `ada/agents/circuit_breaker.py`

Per-agent circuit breaker with three states:
- **Closed** (normal): Requests pass through. Track failure count.
- **Open** (tripped): 5 failures within 60 seconds → open. All requests short-circuit to fallback. Publishes `AGENT_ERROR` event.
- **Half-open** (probe): After 120 seconds, allow one request through. Success → closed. Failure → open again.

Configurable thresholds in `config/default.toml`:
```toml
[resilience.circuit_breaker]
failure_threshold = 5
failure_window_seconds = 60
recovery_timeout_seconds = 120
```

#### Frontend: Error Display

**New event type:** `AGENT_ERROR` added to `ada/core/events.py`. Fields: `agent_name`, `error_type` (timeout/llm_error/circuit_open), `user_message` (optional).

**Chat WS relay:** `AGENT_ERROR` events subscribed in chat WebSocket handler (same pattern as `EMOTION_FUSED`). Only relayed for user-facing agents (WellnessCompanion, CognitiveAssessor, CrisisMonitor).

**Frontend rendering:** Error messages appear inline in the chat stream as a system message with amber styling. Auto-dismiss after 10 seconds. Example: "⚠ Ada is having trouble responding. Try sending another message."

---

## Phase 11b — Features

### 4. Account Recovery

**Goal:** Users can reset their password via a token-based flow. Closes GitHub Issue #19.

#### Database

New table `password_resets`:
```sql
CREATE TABLE password_resets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_password_resets_token ON password_resets(token_hash);
```

Token stored as SHA-256 hash. Raw token sent to user, hash stored in DB. Constant-time comparison on verification.

#### API Endpoints

**`POST /api/auth/forgot-password`**
- Request: `{ "email": "user@example.com" }`
- Always returns 200 (prevents email enumeration)
- If user exists: generates 32-byte random token, stores hash with 1-hour expiry, delivers token
- Rate limit: 3 requests per email per hour
- Token delivery: `EmailTransport` ABC with `ConsoleTransport` (logs to stdout) as default implementation. Pluggable for real SMTP later.

**`POST /api/auth/reset-password`**
- Request: `{ "token": "raw-token-string", "new_password": "..." }`
- Validates: token exists, not expired, not used
- On success: hashes new password, updates user, marks token as used, revokes all refresh tokens for that user
- Returns 200 on success, 400 on invalid/expired token

#### Frontend

- "Forgot password?" link below login form → `ForgotPassword.tsx` (email input → submit → success message)
- Reset link format: `/#/reset-password?token=<token>` → `ResetPassword.tsx` (new password + confirm → submit → redirect to login)
- In dev mode, console shows: "Password reset link: http://localhost:5173/#/reset-password?token=abc123"

### 5. Notification Polish

**Goal:** Users control which notifications they receive. Duplicate notifications are suppressed. No notification spam.

#### Database

New table `notification_preferences`:
```sql
CREATE TABLE notification_preferences (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
    preferences TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

`preferences` JSON structure:
```json
{
  "crisis_detected": true,
  "session_ended": true,
  "daily_summary": true,
  "board_item_added": false,
  "board_item_approved": true,
  "medication_due": true
}
```

Defaults: all enabled. Users opt out of specific event types.

#### API Endpoints

**`GET /api/notifications/preferences`** — Returns current user's preferences (defaults if no row exists).

**`PUT /api/notifications/preferences`** — Accepts partial update: `{ "board_item_added": false }`. Merges with existing preferences.

#### Deduplication

In-memory dict in `NotificationDispatcher`: `recent_notifications: dict[tuple[str, str, str], float]` keyed by `(user_id, event_type, entity_id)` → timestamp.

Before sending, check if same key was sent within 5 minutes. If so, skip. Cleanup stale entries every 10 minutes via asyncio task.

`entity_id` extraction: session_id for session events, alert_id for crisis, board_id for board events, patient_id for daily summaries.

#### Per-User Throttling

Counter per user_id, reset hourly. Default max: 20 notifications/hour. Configurable:
```toml
[notifications]
max_per_user_per_hour = 20
dedup_window_seconds = 300
```

When throttle hits, log warning and skip. Critical events (crisis_detected) bypass throttle.

#### Frontend: Notification Preferences UI

New component: `web/src/components/NotificationPreferences.tsx`

Accessible from NotificationBell dropdown → "Settings" link. Renders a toggle grid:
- Row per event type (human-readable labels)
- On/Off toggle per row
- Save button → `PUT /api/notifications/preferences`

#### Integration Tests

- Subscribe → trigger crisis event → verify push payload received
- Set preference off for board_item_added → trigger → verify NOT sent
- Send 21 notifications in quick succession → verify 20th delivered, 21st throttled
- Send duplicate within 5 min → verify deduped

### 6. PWA + LAN Access

**Goal:** Ada is installable on phones/tablets and accessible from any device on the local network.

#### PWA Manifest

New file: `web/public/manifest.json`
```json
{
  "name": "Ada — Wellness Companion",
  "short_name": "Ada",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#3b82f6",
  "icons": [
    { "src": "/icons/ada-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/ada-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

Icons: generate from existing branding or create minimal placeholder (blue circle with "A").

#### Service Worker Upgrade

Extend existing `web/public/sw.js` (currently handles push notifications only):
- **Cache-first** for static assets (`/assets/*`, icons, manifest)
- **Network-first** for API calls (`/api/*`, `/ws/*`)
- **Cache versioning** via `CACHE_VERSION` constant — bust on deploy
- **Offline fallback page** for when network is completely unavailable

#### Install Prompt

New component: `web/src/components/InstallBanner.tsx`

- Captures `beforeinstallprompt` event
- Shows dismissible banner: "Install Ada on your device for quick access"
- "Install" button triggers the native install prompt
- Dismissed state stored in `localStorage` — shown once per session
- Hidden if already in standalone mode (`window.matchMedia('(display-mode: standalone)')`)

#### LAN Dev Mode

New config section in `config/default.toml`:
```toml
[network]
bind_host = "127.0.0.1"      # "0.0.0.0" for LAN access
cors_origins = ["http://localhost:5173"]
# Additional origins auto-added in LAN mode
```

New script: `scripts/lan-dev.sh`
1. Detects local IP address
2. Generates self-signed cert via `mkcert` (if installed) for `<local-ip>` + `localhost`
3. Starts backend with `bind_host = 0.0.0.0`, adds `https://<local-ip>:5173` to CORS
4. Starts Vite with `--host 0.0.0.0` and `--https` (using mkcert certs)
5. Prints LAN URL and QR code (via `qrencode` if available, otherwise plain URL)

HTTPS is required for: service worker registration, Web Push API, camera/microphone access on non-localhost origins.

---

## Verification Plan

### Phase 11a Verification

1. **Frontend tests:** `cd web && npx vitest run` — all ~40-50 tests pass
2. **WebSocket resilience:**
   - Start a chat session
   - Kill the backend server
   - Verify amber "Reconnecting..." banner appears
   - Restart the backend
   - Verify auto-reconnect, green "Reconnected" banner, queued messages delivered
3. **Agent failure:**
   - Start a session with LLM provider disabled/unreachable
   - Send a message
   - Verify inline error toast appears in chat
   - Verify CrisisMonitor publishes HIGH alert on error (check crisis_alerts table)

### Phase 11b Verification

4. **Account recovery:**
   - Click "Forgot password?" on login
   - Enter registered email
   - Copy token from console output
   - Navigate to reset URL
   - Set new password
   - Login with new password succeeds
   - Login with old password fails
5. **Notification polish:**
   - Open notification preferences, disable `board_item_added`
   - Add a board item from another user → verify NO push received
   - Re-enable → add another → verify push received
   - Trigger same event twice within 5 min → verify only one push
6. **PWA + LAN:**
   - Run `scripts/lan-dev.sh`
   - Scan QR code on phone
   - Verify app loads over HTTPS on phone browser
   - Verify install prompt appears
   - Install → verify standalone mode works
   - Test camera/mic access on phone (requires HTTPS — verify it works)

---

## Files Modified (Summary)

### New Files
- `web/vitest.config.ts`
- `web/test/setup.ts`
- `web/test/msw/handlers.ts`
- `web/test/factories.ts`
- `web/src/hooks/useReconnectingWebSocket.ts`
- `web/src/components/ConnectionStatus.tsx`
- `web/src/components/ForgotPassword.tsx`
- `web/src/components/ResetPassword.tsx`
- `web/src/components/NotificationPreferences.tsx`
- `web/src/components/InstallBanner.tsx`
- `web/public/manifest.json`
- `web/public/icons/ada-192.png`, `ada-512.png`
- `ada/agents/error_handler.py`
- `ada/agents/circuit_breaker.py`
- `ada/api/routes/password_reset.py`
- `scripts/lan-dev.sh`
- `tests/unit/test_circuit_breaker.py`
- `tests/unit/test_password_reset.py`
- `tests/unit/test_notification_preferences.py`
- `tests/integration/test_password_reset_flow.py`
- `tests/integration/test_notification_polish.py`
- `web/src/test/` — 6 component test files

### Modified Files
- `web/package.json` — add vitest, RTL, msw, user-event
- `web/src/hooks/useChat.ts` — switch to useReconnectingWebSocket
- `web/src/hooks/useBoardWebSocket.ts` — switch to useReconnectingWebSocket
- `web/src/App.tsx` — add ConnectionStatus, InstallBanner, reset password route
- `web/src/components/Login.tsx` — add "Forgot password?" link
- `web/src/components/NotificationBell.tsx` — add "Settings" link to preferences
- `web/public/sw.js` — add cache-first/network-first strategies
- `web/index.html` — add manifest link, theme-color meta
- `ada/agents/base.py` — integrate timeout wrapper and circuit breaker
- `ada/core/events.py` — add AGENT_ERROR event type
- `ada/core/state.py` — add password_resets and notification_preferences tables
- `ada/api/app.py` — register password_reset router
- `ada/api/routes/notifications.py` — add preferences endpoints
- `ada/notifications/dispatcher.py` — add dedup, throttle, preferences check
- `config/default.toml` — add resilience and network sections
