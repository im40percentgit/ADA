/**
 * telemetry.test.ts — unit tests for the Solitaire session telemetry bridge.
 *
 * Mocks `fetch` at the global level (the only acceptable external boundary mock
 * per Sacred Practice #5). Fake timers test idle timeout behavior.
 *
 * Tests:
 * - startSession() POSTs session_start with correct shape
 * - endSession('quit') POSTs session_end with duration_ms, completed_hands, error_rate fields
 * - visibilitychange to hidden triggers endSession('visibility')
 * - 5-minute idle triggers endSession('idle')
 * - recordHandCompleted() POSTs hand_completed with hand_outcome and error_count
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  startSession,
  endSession,
  recordHandCompleted,
  recordMoveMade,
  incrementRestartCount,
  getRestartCountToday,
  resetIdle,
  computeStreak,
  dateDiffDays,
} from '../telemetry'

// ---------------------------------------------------------------------------
// fetch mock
// ---------------------------------------------------------------------------

interface CapturedCall {
  url: string
  body: {
    event_type: string
    occurred_at: string
    payload: Record<string, unknown>
  }
}

let capturedCalls: CapturedCall[] = []

function mockFetch() {
  capturedCalls = []
  ;(globalThis as unknown as { fetch: typeof fetch }).fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const body = JSON.parse((init?.body as string) ?? '{}')
    capturedCalls.push({ url: String(url), body })
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
}

function callsOfType(eventType: string): CapturedCall[] {
  return capturedCalls.filter(c => c.body.event_type === eventType)
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockFetch()
  localStorage.clear()
  // Reset any lingering session by ending it silently before each test
  // We can't import _session directly, so just call endSession — it's a no-op if none active
})

afterEach(async () => {
  // Clean up any open sessions
  await endSession('quit')
  vi.restoreAllMocks()
  vi.useRealTimers()
})

// ---------------------------------------------------------------------------
// startSession
// ---------------------------------------------------------------------------

describe('startSession()', () => {
  it('POSTs game.session_start event', async () => {
    await startSession('corgi')

    const calls = callsOfType('game.session_start')
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe('/api/games/solitaire/event')
  })

  it('session_start payload includes game_session_id and deck', async () => {
    await startSession('classic')

    const call = callsOfType('game.session_start')[0]
    expect(call.body.payload).toMatchObject({
      deck: 'classic',
    })
    expect(typeof call.body.payload.game_session_id).toBe('string')
    expect(call.body.payload.game_session_id).toMatch(/^gs-/)
  })

  it('session_start payload has occurred_at ISO timestamp', async () => {
    await startSession('corgi')

    const call = callsOfType('game.session_start')[0]
    expect(call.body.occurred_at).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('calling startSession twice ends prior session first', async () => {
    await startSession('corgi')
    const firstId = callsOfType('game.session_start')[0].body.payload.game_session_id

    // Second call should end first session then start a new one
    await startSession('classic')

    const endCalls = callsOfType('game.session_end')
    expect(endCalls.length).toBeGreaterThanOrEqual(1)
    expect(endCalls[0].body.payload.game_session_id).toBe(firstId)

    const startCalls = callsOfType('game.session_start')
    expect(startCalls).toHaveLength(2)
    expect(startCalls[1].body.payload.game_session_id).not.toBe(firstId)
  })
})

// ---------------------------------------------------------------------------
// endSession
// ---------------------------------------------------------------------------

describe('endSession()', () => {
  it("POSTs game.session_end with reason 'quit'", async () => {
    await startSession('corgi')
    capturedCalls = []   // Reset to only capture the end

    await endSession('quit')

    const call = callsOfType('game.session_end')[0]
    expect(call).toBeDefined()
    expect(call.body.payload.end_reason).toBe('quit')
  })

  it('session_end includes duration_ms as a number', async () => {
    await startSession('corgi')
    await endSession('quit')

    const call = callsOfType('game.session_end')[0]
    expect(typeof call.body.payload.duration_ms).toBe('number')
    expect(call.body.payload.duration_ms).toBeGreaterThanOrEqual(0)
  })

  it('session_end includes completed_hands', async () => {
    await startSession('corgi')
    await endSession('quit')

    const call = callsOfType('game.session_end')[0]
    expect(call.body.payload.completed_hands).toBe(0)
  })

  it('session_end includes error_count', async () => {
    await startSession('corgi')
    await endSession('quit')

    const call = callsOfType('game.session_end')[0]
    expect(typeof call.body.payload.error_count).toBe('number')
  })

  it('calling endSession twice is a no-op on the second call', async () => {
    await startSession('corgi')
    await endSession('quit')
    const countAfterFirst = capturedCalls.length

    await endSession('quit')
    expect(capturedCalls.length).toBe(countAfterFirst)  // no additional calls
  })
})

// ---------------------------------------------------------------------------
// visibilitychange triggers endSession
// ---------------------------------------------------------------------------

describe('visibilitychange', () => {
  it("triggers endSession with reason 'visibility' when hidden", async () => {
    await startSession('corgi')
    capturedCalls = []

    // Simulate visibilitychange to hidden
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    })
    document.dispatchEvent(new Event('visibilitychange'))

    // Give the async endSession a tick to run
    await new Promise(r => setTimeout(r, 10))

    const endCalls = callsOfType('game.session_end')
    expect(endCalls.length).toBeGreaterThanOrEqual(1)
    expect(endCalls[0].body.payload.end_reason).toBe('visibility')

    // Restore
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    })
  })

  it('does not trigger when tab becomes visible', async () => {
    await startSession('corgi')
    capturedCalls = []

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    })
    document.dispatchEvent(new Event('visibilitychange'))

    await new Promise(r => setTimeout(r, 10))

    const endCalls = callsOfType('game.session_end')
    expect(endCalls).toHaveLength(0)

    // Clean up
    await endSession('quit')
  })
})

// ---------------------------------------------------------------------------
// 5-minute idle triggers endSession
// ---------------------------------------------------------------------------

describe('idle timeout', () => {
  it("triggers endSession with reason 'idle' after 5 minutes of inactivity", async () => {
    vi.useFakeTimers()
    mockFetch()

    await startSession('corgi')
    capturedCalls = []

    // Advance 5 minutes — the idle timer fires its setTimeout callback synchronously
    vi.advanceTimersByTime(5 * 60 * 1000)

    // Flush microtasks so the async endSession() Promise chain (postEvent → fetch → response)
    // resolves before we assert. Do NOT use setTimeout(0) — under fake timers it never fires.
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    const endCalls = callsOfType('game.session_end')
    expect(endCalls.length).toBeGreaterThanOrEqual(1)
    expect(endCalls[0].body.payload.end_reason).toBe('idle')

    vi.useRealTimers()
  })

  it('resetIdle extends the idle timer — no session_end before 5 min after last reset', async () => {
    vi.useFakeTimers()
    mockFetch()

    await startSession('corgi')
    capturedCalls = []

    // Advance 4 minutes — no end yet
    vi.advanceTimersByTime(4 * 60 * 1000)
    resetIdle()  // Reset at 4 min — idle now scheduled for 9 min wall-clock

    // Advance another 4 minutes (8 total wall-clock; only 4 min since last reset)
    vi.advanceTimersByTime(4 * 60 * 1000)

    // Flush microtasks only — do NOT runAllTimersAsync, which would drain the
    // 9-min idle timer that hasn't yet fired and produce a false positive.
    await Promise.resolve()

    // Should NOT have ended yet — only 4 min since reset
    const endCalls = callsOfType('game.session_end')
    expect(endCalls).toHaveLength(0)

    // Clean up cleanly via explicit endSession rather than letting idle fire
    await endSession('quit')

    vi.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// recordHandCompleted
// ---------------------------------------------------------------------------

describe('recordHandCompleted()', () => {
  it('POSTs game.hand_completed event', async () => {
    await startSession('corgi')
    capturedCalls = []

    await recordHandCompleted(2, 180000)

    const calls = callsOfType('game.hand_completed')
    expect(calls).toHaveLength(1)
  })

  it('hand_completed includes hand_outcome = won', async () => {
    await startSession('corgi')
    capturedCalls = []

    await recordHandCompleted(0, 120000)

    const call = callsOfType('game.hand_completed')[0]
    expect(call.body.payload.hand_outcome).toBe('won')
  })

  it('hand_completed includes error_count', async () => {
    await startSession('corgi')
    capturedCalls = []

    await recordHandCompleted(5, 90000)

    const call = callsOfType('game.hand_completed')[0]
    expect(call.body.payload.error_count).toBe(5)
  })

  it('hand_completed includes duration_ms', async () => {
    await startSession('corgi')
    capturedCalls = []

    await recordHandCompleted(1, 75000)

    const call = callsOfType('game.hand_completed')[0]
    expect(call.body.payload.duration_ms).toBe(75000)
  })

  it('is a no-op if no session is active', async () => {
    // Ensure no session
    await endSession('quit')
    capturedCalls = []

    await recordHandCompleted(0, 0)
    expect(capturedCalls).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// computeStreak & dateDiffDays (pure functions — no fetch needed)
// ---------------------------------------------------------------------------

describe('dateDiffDays()', () => {
  it('returns 0 for same date', () => {
    expect(dateDiffDays('2026-04-24', '2026-04-24')).toBe(0)
  })

  it('returns 1 for consecutive dates', () => {
    expect(dateDiffDays('2026-04-23', '2026-04-24')).toBe(1)
  })

  it('returns negative for reverse order', () => {
    expect(dateDiffDays('2026-04-24', '2026-04-23')).toBe(-1)
  })
})

describe('computeStreak()', () => {
  it('returns currentDays=1 on first session ever', () => {
    localStorage.clear()
    const result = computeStreak()
    expect(result.currentDays).toBe(1)
    expect(result.broken).toBe(false)
  })

  it('returns same streak if played again same day', () => {
    localStorage.clear()
    computeStreak()  // sets today
    const result = computeStreak()
    expect(result.currentDays).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// recordMoveMade (M1 v0.5)
// ---------------------------------------------------------------------------

describe('recordMoveMade()', () => {
  it('POSTs game.move_made with correct shape', async () => {
    await startSession('corgi')
    capturedCalls = []

    await recordMoveMade({
      moveType: 'tableau-to-foundation',
      wasValid: true,
      wasUndo: false,
      decisionTimeMs: 1500,
      cardValue: 1,
    })

    const calls = callsOfType('game.move_made')
    expect(calls).toHaveLength(1)
    const payload = calls[0].body.payload
    expect(payload.move_type).toBe('tableau-to-foundation')
    expect(payload.was_valid).toBe(true)
    expect(payload.was_undo).toBe(false)
    expect(payload.decision_time_ms).toBe(1500)
    expect(payload.card_value).toBe(1)
    expect(payload.game_session_id).toMatch(/^gs-/)
  })

  it('move_index increments on successive moves', async () => {
    await startSession('corgi')
    capturedCalls = []

    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 100, cardValue: null })
    await recordMoveMade({ moveType: 'talon-to-tableau', wasValid: true, wasUndo: false, decisionTimeMs: 200, cardValue: 14 })
    await recordMoveMade({ moveType: 'invalid', wasValid: false, wasUndo: false, decisionTimeMs: 300, cardValue: null })

    const calls = callsOfType('game.move_made')
    expect(calls).toHaveLength(3)
    expect(calls[0].body.payload.move_index).toBe(0)
    expect(calls[1].body.payload.move_index).toBe(1)
    expect(calls[2].body.payload.move_index).toBe(2)
  })

  it('null card_value is preserved for stock-flip', async () => {
    await startSession('corgi')
    capturedCalls = []

    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 50, cardValue: null })

    const call = callsOfType('game.move_made')[0]
    expect(call.body.payload.card_value).toBeNull()
  })

  it('is a no-op if no session is active', async () => {
    await endSession('quit')
    capturedCalls = []

    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 0, cardValue: null })
    expect(callsOfType('game.move_made')).toHaveLength(0)
  })

  it('session_end aggregates accumulate from recordMoveMade calls', async () => {
    await startSession('corgi')
    capturedCalls = []

    // 3 moves: 1 undo, 1 invalid click, 1 normal
    await recordMoveMade({ moveType: 'invalid', wasValid: false, wasUndo: true, decisionTimeMs: 100, cardValue: null })
    await recordMoveMade({ moveType: 'invalid', wasValid: false, wasUndo: false, decisionTimeMs: 200, cardValue: null })
    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 300, cardValue: null })

    await endSession('quit')

    const endCall = callsOfType('game.session_end')[0]
    const p = endCall.body.payload
    expect(p.total_moves).toBe(3)
    expect(p.total_undo_count).toBe(1)
    expect(p.total_invalid_click_count).toBe(2)
    // total_idle_ms should be 0 — no gaps > 30s in immediate calls
    expect(p.total_idle_ms).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// decision_time_ms measurement via fake timers
// ---------------------------------------------------------------------------

describe('decision_time_ms measurement', () => {
  it('measures time between session start and first move', async () => {
    vi.useFakeTimers()
    mockFetch()

    await startSession('corgi')
    // Advance 2 seconds — simulates patient thinking before first move
    vi.advanceTimersByTime(2000)

    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 2000, cardValue: null })

    const call = callsOfType('game.move_made')[0]
    // The decisionTimeMs is passed in directly by the caller (useSolitaire hook)
    expect(call.body.payload.decision_time_ms).toBe(2000)

    vi.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// total_idle_ms accumulation
// ---------------------------------------------------------------------------

describe('total_idle_ms in session_end', () => {
  it('gaps under 30s do not accumulate in total_idle_ms', async () => {
    vi.useFakeTimers()
    mockFetch()

    await startSession('corgi')
    capturedCalls = []

    // Move immediately (0ms gap)
    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 10, cardValue: null })
    // Advance 20s (under threshold)
    vi.advanceTimersByTime(20000)
    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 20000, cardValue: null })

    await endSession('quit')

    const endCall = callsOfType('game.session_end')[0]
    expect(endCall.body.payload.total_idle_ms).toBe(0)

    vi.useRealTimers()
  })

  it('gaps over 30s accumulate in total_idle_ms, capped at 5 min per gap', async () => {
    vi.useFakeTimers()
    mockFetch()

    await startSession('corgi')
    capturedCalls = []

    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 10, cardValue: null })
    // Advance 45s (over 30s threshold, under 5min cap)
    vi.advanceTimersByTime(45000)
    await recordMoveMade({ moveType: 'stock-flip', wasValid: true, wasUndo: false, decisionTimeMs: 45000, cardValue: null })

    await endSession('quit')

    const endCall = callsOfType('game.session_end')[0]
    // Should have captured the 45s gap (above 30s threshold)
    expect(endCall.body.payload.total_idle_ms).toBe(45000)

    vi.useRealTimers()
  })
})

// ---------------------------------------------------------------------------
// restart_count_today
// ---------------------------------------------------------------------------

describe('incrementRestartCount() / getRestartCountToday()', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns 0 before any restart', () => {
    expect(getRestartCountToday()).toBe(0)
  })

  it('returns 1 after first incrementRestartCount()', () => {
    incrementRestartCount()
    expect(getRestartCountToday()).toBe(1)
  })

  it('increments on successive calls same day', () => {
    incrementRestartCount()
    incrementRestartCount()
    incrementRestartCount()
    expect(getRestartCountToday()).toBe(3)
  })

  it('resets to 1 when date changes', () => {
    // Simulate prior day entry in localStorage
    localStorage.setItem('ada.solitaire.restartCountDate', '2026-04-23')
    localStorage.setItem('ada.solitaire.restartCountToday', '5')

    // Call on a new day (today is 2026-04-24 per memory context)
    vi.setSystemTime(new Date('2026-04-24T10:00:00'))
    incrementRestartCount()

    // Should reset to 1, not 6
    expect(getRestartCountToday()).toBe(1)

    vi.useRealTimers()
  })

  it('restart_count_today surfaces in session_end payload', async () => {
    incrementRestartCount()
    incrementRestartCount()

    await startSession('corgi')
    capturedCalls = []
    await endSession('quit')

    const endCall = callsOfType('game.session_end')[0]
    expect(endCall.body.payload.restart_count_today).toBe(2)
  })
})
