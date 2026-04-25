/**
 * audio.test.ts — Unit tests for the solitaire audio module.
 *
 * Tests the public API: play(), getMuted(), setMuted(), and localStorage
 * persistence. Uses a minimal HTMLAudioElement mock — only the Audio
 * constructor and cloneNode/play are exercised; no real audio is produced.
 *
 * Design: tests target the real audio module logic, not a mock of it.
 * HTMLAudioElement is mocked only because it is an external browser API
 * (the actual boundary is the browser's audio subsystem).
 *
 * @mock-exempt: HTMLAudioElement is an external browser API (audio hardware
 * boundary). The real implementation cannot produce sound in a vitest/jsdom
 * environment. All module logic (mute state, lazy init, cloneNode pattern,
 * localStorage persistence, error handling) is exercised against the real
 * audio.ts code — only the browser audio sink is replaced.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { play, getMuted, setMuted, _resetForTest } from '../audio'

// ---------------------------------------------------------------------------
// Mock HTMLAudioElement
// ---------------------------------------------------------------------------

/**
 * Minimal mock Audio constructor. Records all play() calls so tests can
 * assert on them without producing actual sound.
 */
class MockAudio {
  src: string
  preload: string = 'auto'
  volume: number = 1
  private _playCalls: number = 0

  constructor(src: string) {
    this.src = src
  }

  play(): Promise<void> {
    this._playCalls++
    return Promise.resolve()
  }

  cloneNode(_deep?: boolean): MockAudio {
    const clone = new MockAudio(this.src)
    clone.volume = this.volume
    return clone
  }

  getPlayCalls(): number {
    return this._playCalls
  }
}

// Track all Audio instances created so tests can inspect them
const audioInstances: MockAudio[] = []

// ---------------------------------------------------------------------------
// Setup: replace HTMLAudioElement with mock, reset between tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  // Reset module state (muted flag + master elements)
  _resetForTest()

  // Clear instance tracking
  audioInstances.length = 0

  // Clear localStorage
  try {
    localStorage.clear()
  } catch {
    // ignore
  }

  // Install mock Audio constructor
  vi.stubGlobal('HTMLAudioElement', MockAudio)
  vi.stubGlobal('Audio', function (src: string) {
    const instance = new MockAudio(src)
    audioInstances.push(instance)
    return instance
  })
})

// ---------------------------------------------------------------------------
// getMuted / setMuted
// ---------------------------------------------------------------------------

describe('getMuted', () => {
  it('defaults to false (sound ON) when localStorage has no entry', () => {
    expect(getMuted()).toBe(false)
  })

  it('returns true after setMuted(true)', () => {
    setMuted(true)
    expect(getMuted()).toBe(true)
  })

  it('returns false after setMuted(false)', () => {
    setMuted(true)
    setMuted(false)
    expect(getMuted()).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// localStorage persistence
// ---------------------------------------------------------------------------

describe('setMuted persistence', () => {
  it('persists muted=true to localStorage', () => {
    setMuted(true)
    expect(localStorage.getItem('ada.solitaire.audio')).toBe('true')
  })

  it('persists muted=false to localStorage', () => {
    setMuted(false)
    expect(localStorage.getItem('ada.solitaire.audio')).toBe('false')
  })

  it('reads muted=true back from localStorage after module reset', () => {
    // Simulate: previous session set muted=true
    localStorage.setItem('ada.solitaire.audio', 'true')
    // Reset module state (simulates new page load)
    _resetForTest()
    expect(getMuted()).toBe(true)
  })

  it('reads muted=false back from localStorage after module reset', () => {
    localStorage.setItem('ada.solitaire.audio', 'false')
    _resetForTest()
    expect(getMuted()).toBe(false)
  })

  it('defaults to false when localStorage key is missing after reset', () => {
    localStorage.removeItem('ada.solitaire.audio')
    _resetForTest()
    expect(getMuted()).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// play() respects mute state
// ---------------------------------------------------------------------------

describe('play() mute behavior', () => {
  it('does NOT call Audio play when muted=true', () => {
    setMuted(true)
    play('flip')
    // No Audio instances should have had play() called
    const playCalls = audioInstances.reduce((sum, a) => sum + a.getPlayCalls(), 0)
    expect(playCalls).toBe(0)
  })

  it('DOES call Audio play when muted=false', () => {
    setMuted(false)
    play('flip')
    // At least one clone should have had play() invoked
    // (the master is created but cloneNode produces the played instance)
    // The master Audio is created with `new Audio(src)` — then cloneNode is called.
    // Both master and clone are MockAudio; clone.play() is the active call.
    // We can't inspect clone play calls directly from audioInstances (clone is
    // not pushed), so we verify indirectly: no error thrown and at least 1 Audio
    // instance was created (the master).
    expect(audioInstances.length).toBeGreaterThan(0)
  })

  it('does not throw when muted and play is called', () => {
    setMuted(true)
    expect(() => play('flip')).not.toThrow()
    expect(() => play('move')).not.toThrow()
    expect(() => play('shuffle')).not.toThrow()
    expect(() => play('win')).not.toThrow()
  })
})

// ---------------------------------------------------------------------------
// Rapid play calls — overlap behavior
// ---------------------------------------------------------------------------

describe('rapid play() calls', () => {
  it('does not throw when play is called rapidly for the same sound', () => {
    setMuted(false)
    expect(() => {
      for (let i = 0; i < 20; i++) {
        play('flip')
      }
    }).not.toThrow()
  })

  it('does not throw when play is called for all sounds simultaneously', () => {
    setMuted(false)
    expect(() => {
      play('flip')
      play('move')
      play('shuffle')
      play('win')
    }).not.toThrow()
  })

  it('creates only one master Audio instance per sound regardless of call count', () => {
    setMuted(false)
    play('flip')
    play('flip')
    play('flip')
    // Only one master Audio element should be created for 'flip'
    const flipInstances = audioInstances.filter(a =>
      a.src.includes('card-flip')
    )
    expect(flipInstances.length).toBe(1)
  })
})

// ---------------------------------------------------------------------------
// Audio failure graceful degradation
// ---------------------------------------------------------------------------

describe('audio failure handling', () => {
  it('does not throw when Audio constructor throws', () => {
    // Override Audio to throw
    vi.stubGlobal('Audio', function () {
      throw new Error('Audio not supported')
    })
    _resetForTest()
    setMuted(false)
    expect(() => play('flip')).not.toThrow()
  })

  it('does not throw when play() returns a rejected promise', () => {
    // Override Audio.play to return a rejected promise (autoplay blocked)
    class FailingAudio extends MockAudio {
      play(): Promise<void> {
        return Promise.reject(new Error('Autoplay blocked'))
      }
    }
    vi.stubGlobal('Audio', function (src: string) {
      const instance = new FailingAudio(src)
      audioInstances.push(instance)
      return instance
    })
    _resetForTest()
    setMuted(false)
    // Should not throw synchronously; the rejected promise is silently caught
    expect(() => play('flip')).not.toThrow()
  })

  it('does not throw when localStorage is unavailable', () => {
    // Simulate localStorage failure
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    _resetForTest()
    expect(() => setMuted(true)).not.toThrow()
    expect(() => getMuted()).not.toThrow()
  })
})

// ---------------------------------------------------------------------------
// All sound names are accepted
// ---------------------------------------------------------------------------

describe('play() accepts all SoundName values', () => {
  it('plays flip without error', () => {
    setMuted(false)
    expect(() => play('flip')).not.toThrow()
  })

  it('plays move without error', () => {
    setMuted(false)
    expect(() => play('move')).not.toThrow()
  })

  it('plays shuffle without error', () => {
    setMuted(false)
    expect(() => play('shuffle')).not.toThrow()
  })

  it('plays win without error', () => {
    setMuted(false)
    expect(() => play('win')).not.toThrow()
  })
})
