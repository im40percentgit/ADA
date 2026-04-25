/**
 * Solitaire session telemetry — emits events to the Ada backend.
 *
 * Session lifecycle:
 * 1. Call `startSession()` when the patient opens the game.
 * 2. Call `recordHandCompleted()` each time they win a hand.
 * 3. Session ends automatically via:
 *    (a) `endSession('quit')` — explicit navigation away
 *    (b) visibilitychange → hidden — tab switch, app switch, lock screen
 *    (c) 5-minute idle — no card interaction for IDLE_TIMEOUT_MS
 *
 * All events are POSTed to POST /api/games/solitaire/event.
 *
 * @decision DEC-GAMES-004
 * @title visibilitychange not beforeunload for session_end
 * @status accepted
 * @rationale beforeunload is unreliable on iOS Safari (fires too late or not
 *   at all for PWA home-screen launches). visibilitychange fires reliably on
 *   app-switch, home-screen tap, and lock screen. Periodic heartbeat kept
 *   simple — idle timer resets on any card interaction via resetIdle().
 *
 * @decision DEC-GAMES-005
 * @title JSON payload column — event shapes defined here match backend schema
 * @status accepted
 * @rationale Payload fields match GameSessionEndEvent/GameHandCompletedEvent
 *   dataclasses in ada/core/events.py. Any new fields added here must be
 *   reflected in the backend dataclass to avoid silent data loss.
 */

const IDLE_TIMEOUT_MS = 5 * 60 * 1000   // 5 minutes

// ---------------------------------------------------------------------------
// Event type constants (must match ada/core/events.py EventTypes)
// ---------------------------------------------------------------------------

const ET_SESSION_START = 'game.session_start'
const ET_SESSION_END = 'game.session_end'
const ET_HAND_COMPLETED = 'game.hand_completed'
const ET_STREAK = 'game.engagement_streak'

// ---------------------------------------------------------------------------
// Internal session state
// ---------------------------------------------------------------------------

interface SessionState {
  gameSessionId: string
  startTime: number
  completedHands: number
  errorCount: number
  deck: string
  ended: boolean
}

let _session: SessionState | null = null
let _idleTimer: ReturnType<typeof setTimeout> | null = null
let _visHandler: (() => void) | null = null

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

async function postEvent(eventType: string, payload: Record<string, unknown>): Promise<void> {
  try {
    const occurredAt = new Date().toISOString()
    await fetch('/api/games/solitaire/event', {
      method: 'POST',
      // authHeaders() provides Content-Type + optional Authorization
      ...authHeaders(),
      body: JSON.stringify({ event_type: eventType, occurred_at: occurredAt, payload }),
    })
  } catch {
    // Non-blocking — telemetry failures must never break the game
  }
}

function authHeaders(): { headers: Record<string, string> } {
  const token = localStorage.getItem('ada_access_token')
  return token
    ? { headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } }
    : { headers: { 'Content-Type': 'application/json' } }
}

// ---------------------------------------------------------------------------
// Idle timer management
// ---------------------------------------------------------------------------

function clearIdle(): void {
  if (_idleTimer !== null) {
    clearTimeout(_idleTimer)
    _idleTimer = null
  }
}

function scheduleIdle(): void {
  clearIdle()
  _idleTimer = setTimeout(() => {
    void endSession('idle')
  }, IDLE_TIMEOUT_MS)
}

/** Call this on every card interaction to reset the idle timer. */
export function resetIdle(): void {
  if (_session && !_session.ended) {
    scheduleIdle()
  }
}

// ---------------------------------------------------------------------------
// Session lifecycle
// ---------------------------------------------------------------------------

/** Begin a new game session. Safe to call even if a prior session is open. */
export async function startSession(deck: string = 'corgi'): Promise<void> {
  // End any lingering session from a prior game
  if (_session && !_session.ended) {
    await endSession('quit')
  }

  const gameSessionId = `gs-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
  _session = {
    gameSessionId,
    startTime: Date.now(),
    completedHands: 0,
    errorCount: 0,
    deck,
    ended: false,
  }

  // Register visibilitychange handler
  _visHandler = () => {
    if (document.visibilityState === 'hidden' && _session && !_session.ended) {
      void endSession('visibility')
    }
  }
  document.addEventListener('visibilitychange', _visHandler)

  scheduleIdle()

  await postEvent(ET_SESSION_START, {
    game_session_id: gameSessionId,
    deck,
  })
}

/** Record a won hand. Call once when the game engine reports won=true. */
export async function recordHandCompleted(
  handErrorCount: number,
  durationMs: number,
): Promise<void> {
  if (!_session || _session.ended) return
  _session.completedHands += 1

  await postEvent(ET_HAND_COMPLETED, {
    game_session_id: _session.gameSessionId,
    hand_outcome: 'won',
    error_count: handErrorCount,
    duration_ms: durationMs,
  })

  resetIdle()
}

/**
 * Update the session's running error count. Call after each invalid move.
 * This is a local counter — not a separate event.
 */
export function incrementErrorCount(): void {
  if (_session && !_session.ended) {
    _session.errorCount += 1
  }
}

/**
 * End the current session and emit session_end + engagement_streak events.
 *
 * @param reason  'quit' | 'visibility' | 'idle'
 */
export async function endSession(reason: string): Promise<void> {
  if (!_session || _session.ended) return
  _session.ended = true

  clearIdle()
  if (_visHandler) {
    document.removeEventListener('visibilitychange', _visHandler)
    _visHandler = null
  }

  const durationMs = Date.now() - _session.startTime

  await postEvent(ET_SESSION_END, {
    game_session_id: _session.gameSessionId,
    duration_ms: durationMs,
    completed_hands: _session.completedHands,
    error_count: _session.errorCount,
    end_reason: reason,
    deck: _session.deck,
  })

  // Emit streak — compute from local storage to avoid a round-trip.
  // Backend also computes this server-side for the verdict generator;
  // client-side streak is informational for in-game display only.
  const streak = computeStreak()
  await postEvent(ET_STREAK, {
    current_streak_days: streak.currentDays,
    broken_streak: streak.broken,
  })

  _session = null
}

/**
 * Cleanup function for React effects / route changes.
 * Ends the session with reason 'quit'.
 */
export function cleanupSession(): void {
  if (_session && !_session.ended) {
    void endSession('quit')
  }
}

// ---------------------------------------------------------------------------
// Streak computation (client-side, localStorage)
// ---------------------------------------------------------------------------

const STREAK_KEY = 'ada_solitaire_streak'

interface StreakData {
  lastPlayedDate: string   // 'YYYY-MM-DD' in patient-local TZ
  currentDays: number
}

/** Compute engagement streak, updating localStorage. */
export function computeStreak(): { currentDays: number; broken: boolean } {
  const todayLocal = todayLocalDate()
  let broken = false

  try {
    const raw = localStorage.getItem(STREAK_KEY)
    const data: StreakData | null = raw ? JSON.parse(raw) : null

    if (!data) {
      // First ever session
      localStorage.setItem(STREAK_KEY, JSON.stringify({ lastPlayedDate: todayLocal, currentDays: 1 }))
      return { currentDays: 1, broken: false }
    }

    const daysDiff = dateDiffDays(data.lastPlayedDate, todayLocal)

    if (daysDiff === 0) {
      // Already played today — streak unchanged
      return { currentDays: data.currentDays, broken: false }
    } else if (daysDiff === 1) {
      // Consecutive day — increment
      const updated: StreakData = { lastPlayedDate: todayLocal, currentDays: data.currentDays + 1 }
      localStorage.setItem(STREAK_KEY, JSON.stringify(updated))
      return { currentDays: updated.currentDays, broken: false }
    } else {
      // Gap — streak broken
      broken = true
      localStorage.setItem(STREAK_KEY, JSON.stringify({ lastPlayedDate: todayLocal, currentDays: 1 }))
      return { currentDays: 1, broken: true }
    }
  } catch {
    return { currentDays: 0, broken }
  }
}

function todayLocalDate(): string {
  const d = new Date()
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Days between two 'YYYY-MM-DD' date strings. Returns positive if b > a. */
export function dateDiffDays(a: string, b: string): number {
  const msPerDay = 86400000
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / msPerDay)
}
