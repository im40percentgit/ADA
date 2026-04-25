/**
 * Solitaire session telemetry — emits events to the Ada backend.
 *
 * Session lifecycle:
 * 1. Call `startSession()` when the patient opens the game.
 * 2. Call `recordMoveMade()` on every card interaction (valid or invalid).
 * 3. Call `recordHandCompleted()` each time they win a hand.
 * 4. Session ends automatically via:
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
 *
 * @decision DEC-GAMES-008
 * @title Idle gap threshold 30s and 5-min cap for total_idle_ms
 * @status accepted
 * @rationale 30s threshold filters out normal thinking pauses mid-play.
 *   5-min cap aligns with the existing idle-timer's session_end trigger —
 *   gaps longer than 5 min end the session, so uncapped gaps would double-
 *   count idle time that already caused a session boundary.
 */

const IDLE_TIMEOUT_MS = 5 * 60 * 1000   // 5 minutes
const IDLE_GAP_THRESHOLD_MS = 30 * 1000  // 30 seconds — gaps shorter than this are normal play
const IDLE_GAP_CAP_MS = 5 * 60 * 1000   // 5-min cap per gap — aligns with session_end idle trigger

// ---------------------------------------------------------------------------
// Event type constants (must match ada/core/events.py EventTypes)
// ---------------------------------------------------------------------------

const ET_SESSION_START = 'game.session_start'
const ET_SESSION_END = 'game.session_end'
const ET_HAND_COMPLETED = 'game.hand_completed'
const ET_STREAK = 'game.engagement_streak'
const ET_MOVE_MADE = 'game.move_made'

// ---------------------------------------------------------------------------
// Restart count (today) — localStorage keys
//
// Maintained per "New Game" press. Date math in patient's local timezone.
// ---------------------------------------------------------------------------

const RESTART_COUNT_KEY = 'ada.solitaire.restartCountToday'
const RESTART_DATE_KEY = 'ada.solitaire.restartCountDate'

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
  // M1 v0.5 per-move accumulators
  moveIndex: number
  totalUndoCount: number
  totalInvalidClickCount: number
  totalIdleMs: number
  lastMoveTime: number    // timestamp of last move attempt (for gap measurement)
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
  const now = Date.now()
  _session = {
    gameSessionId,
    startTime: now,
    completedHands: 0,
    errorCount: 0,
    deck,
    ended: false,
    // M1 v0.5 per-move accumulators
    moveIndex: 0,
    totalUndoCount: 0,
    totalInvalidClickCount: 0,
    totalIdleMs: 0,
    lastMoveTime: now,   // baseline: session start time
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

// ---------------------------------------------------------------------------
// Per-move telemetry (M1 v0.5)
// ---------------------------------------------------------------------------

export interface MoveMadeParams {
  moveType: string
  wasValid: boolean
  wasUndo: boolean
  /** Time since last render commit (ms). Caller computes via Date.now() - lastRenderTime. */
  decisionTimeMs: number
  /** Card value 1–52, or null for stock-flip / recycle. */
  cardValue: number | null
}

/**
 * Emit a game.move_made event and update per-session accumulators.
 *
 * Call after every card interaction — valid moves, invalid clicks, undos,
 * stock-flips, and recycles all count as "a move was attempted."
 *
 * @decision DEC-GAMES-007
 * @title decision_time_ms measured from last render commit, not session start
 * @status accepted
 * @rationale The patient perceives "when did the new state become visible" as
 *   the decision baseline. Measuring from the last render commit (Date.now()
 *   captured in useSolitaire after each dispatch) matches that perception.
 */
export async function recordMoveMade(params: MoveMadeParams): Promise<void> {
  if (!_session || _session.ended) return

  const now = Date.now()

  // Accumulate idle gap if this move comes after a long pause
  const gap = now - _session.lastMoveTime
  if (gap > IDLE_GAP_THRESHOLD_MS) {
    _session.totalIdleMs += Math.min(gap, IDLE_GAP_CAP_MS)
  }
  _session.lastMoveTime = now

  // Update per-session accumulators
  if (params.wasUndo) _session.totalUndoCount += 1
  if (!params.wasValid) _session.totalInvalidClickCount += 1

  const currentIndex = _session.moveIndex
  _session.moveIndex += 1

  await postEvent(ET_MOVE_MADE, {
    game_session_id: _session.gameSessionId,
    move_index: currentIndex,
    move_type: params.moveType,
    was_valid: params.wasValid,
    was_undo: params.wasUndo,
    decision_time_ms: params.decisionTimeMs,
    card_value: params.cardValue,
  })

  resetIdle()
}

// ---------------------------------------------------------------------------
// Restart count (today) — localStorage, patient-local timezone
// ---------------------------------------------------------------------------

/**
 * Increment today's restart counter. Call on every "New Game" press.
 * Resets automatically when the calendar date changes in patient-local TZ.
 */
export function incrementRestartCount(): void {
  const todayLocal = todayLocalDate()
  try {
    const storedDate = localStorage.getItem(RESTART_DATE_KEY)
    const storedCount = localStorage.getItem(RESTART_COUNT_KEY)
    if (storedDate === todayLocal && storedCount !== null) {
      localStorage.setItem(RESTART_COUNT_KEY, String(parseInt(storedCount, 10) + 1))
    } else {
      // New day (or first ever) — reset to 1
      localStorage.setItem(RESTART_DATE_KEY, todayLocal)
      localStorage.setItem(RESTART_COUNT_KEY, '1')
    }
  } catch {
    // localStorage unavailable — silently skip
  }
}

/** Return today's restart count (0 if never pressed or localStorage unavailable). */
export function getRestartCountToday(): number {
  try {
    const todayLocal = todayLocalDate()
    const storedDate = localStorage.getItem(RESTART_DATE_KEY)
    const storedCount = localStorage.getItem(RESTART_COUNT_KEY)
    if (storedDate === todayLocal && storedCount !== null) {
      return parseInt(storedCount, 10)
    }
    return 0
  } catch {
    return 0
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
    // M1 v0.5 per-move aggregates
    total_moves: _session.moveIndex,
    total_undo_count: _session.totalUndoCount,
    total_invalid_click_count: _session.totalInvalidClickCount,
    total_idle_ms: _session.totalIdleMs,
    restart_count_today: getRestartCountToday(),
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
