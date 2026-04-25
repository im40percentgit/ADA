/**
 * audio.ts — Solitaire sound effects module.
 *
 * Pure module: no React, no DOM beyond HTMLAudioElement.
 * All audio is fire-and-forget via cloneNode() so rapid clicks never cut each
 * other off. Lazy-init on first play() call — avoids loading anything for
 * users who mute immediately, and satisfies iOS Safari's requirement that
 * audio context creation is triggered by a user gesture (the first card
 * interaction is always user-initiated).
 *
 * Volume is capped at 0.6 across all clips (DEC-GAMES-014) to protect
 * elderly and noise-sensitive patients.
 *
 * Mute state is persisted in localStorage under key ada.solitaire.audio
 * (DEC-GAMES-013). Default is unmuted (sound ON) per founder's choice.
 * Gracefully degrades when localStorage is unavailable (Private mode, etc.).
 *
 * Audio playback failures (e.g. browser autoplay policy) are silently
 * swallowed — never throw to the caller.
 *
 * @decision DEC-GAMES-012
 * @title Sound effects shipped at V1 with 4 clips
 * @status accepted
 * @rationale Founder dogfood request; ties into personalization-as-retention
 *   narrative. Bounded scope: 4 clips, one mute toggle, no library deps.
 *
 * @decision DEC-GAMES-013
 * @title Default ON, mute toggle persisted in localStorage
 * @status accepted
 * @rationale Founder explicitly chose default-ON; toggle gives sensory-sensitive
 *   patients (or quiet environments) easy opt-out. Key: ada.solitaire.audio.
 *
 * @decision DEC-GAMES-014
 * @title Lazy-init audio on first user gesture, fire-and-forget, soft fail
 * @status accepted
 * @rationale iOS Safari audio context requirement; rapid card clicks must not
 *   cut each other off (cloneNode pattern); volume cap ~0.6 for patient safety.
 *
 * @decision DEC-GAMES-015
 * @title All audio assets are CC0 / public domain
 * @status accepted
 * @rationale GPL-attachment risk previously surfaced with rejected Jim Blackler
 *   solitaire reference. Explicit license discipline now mandatory. Sources
 *   documented in AUDIO_SOURCES.md.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SoundName = 'flip' | 'move' | 'shuffle' | 'win'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AUDIO_LS_KEY = 'ada.solitaire.audio'
const VOLUME = 0.6

/**
 * Map from SoundName to the public asset path.
 * Paths are relative to the web server root — Vite serves public/ at /.
 */
const SOUND_PATHS: Record<SoundName, string> = {
  flip:    '/games/solitaire/audio/card-flip.mp3',
  move:    '/games/solitaire/audio/card-move.mp3',
  shuffle: '/games/solitaire/audio/shuffle.mp3',
  win:     '/games/solitaire/audio/game-won.mp3',
}

// ---------------------------------------------------------------------------
// Module-level state
// ---------------------------------------------------------------------------

/**
 * Master audio elements, lazy-initialized on first play() call.
 * Each call to play() clones the master element to allow overlap.
 */
const masters: Partial<Record<SoundName, HTMLAudioElement>> = {}

/** Muted state. Initialized lazily from localStorage on first access. */
let _muted: boolean | null = null

// ---------------------------------------------------------------------------
// localStorage helpers — both guard against Private mode / quota errors
// ---------------------------------------------------------------------------

function readMutedFromStorage(): boolean {
  try {
    const val = localStorage.getItem(AUDIO_LS_KEY)
    // Stored as 'true' / 'false'. Missing key → default false (sound ON).
    return val === 'true'
  } catch {
    return false
  }
}

function writeMutedToStorage(muted: boolean): void {
  try {
    localStorage.setItem(AUDIO_LS_KEY, String(muted))
  } catch {
    // Private mode or storage full — ignore
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Returns current mute state. Defaults to false (sound ON) on first call.
 */
export function getMuted(): boolean {
  if (_muted === null) {
    _muted = readMutedFromStorage()
  }
  return _muted
}

/**
 * Sets mute state and persists to localStorage.
 */
export function setMuted(muted: boolean): void {
  _muted = muted
  writeMutedToStorage(muted)
}

/**
 * Lazy-initializes the master HTMLAudioElement for a sound name.
 * Returns null if HTMLAudioElement is unavailable (SSR / test env without DOM).
 */
function getMaster(name: SoundName): HTMLAudioElement | null {
  if (masters[name]) return masters[name]!

  // Guard: HTMLAudioElement may not exist in test environments
  if (typeof HTMLAudioElement === 'undefined') return null

  try {
    const el = new Audio(SOUND_PATHS[name])
    el.preload = 'auto'
    el.volume = VOLUME
    masters[name] = el
    return el
  } catch {
    return null
  }
}

/**
 * Plays a sound effect fire-and-forget style.
 *
 * - Does nothing if muted.
 * - Clones the master element so rapid calls overlap (no cutoff).
 * - Swallows all errors silently (autoplay policy, missing file, etc.).
 */
export function play(name: SoundName): void {
  if (getMuted()) return

  const master = getMaster(name)
  if (!master) return

  try {
    // cloneNode(false) copies the src/volume but creates an independent
    // playback instance. Each clone plays independently and is GC'd when done.
    const instance = master.cloneNode(false) as HTMLAudioElement
    instance.volume = VOLUME
    const promise = instance.play()
    // play() returns a Promise in modern browsers — silence unhandled rejection
    if (promise !== undefined) {
      promise.catch(() => { /* autoplay blocked or other error — silent fail */ })
    }
  } catch {
    // Synchronous throw (rare, e.g. detached document) — silent fail
  }
}

/**
 * Resets module state. Used in tests only.
 * @internal
 */
export function _resetForTest(): void {
  for (const key of Object.keys(masters) as SoundName[]) {
    delete masters[key]
  }
  _muted = null
}
