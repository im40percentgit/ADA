/**
 * useCompanionPreferences — React hook for companion persona preferences.
 *
 * Fetches the authenticated user's companion preferences (name, voice,
 * personality traits) on mount and exposes an update() function for
 * partial updates that optimistically refresh local state.
 *
 * @decision DEC-COMPANION-002
 * @title useCompanionPreferences hook follows useNotifications pattern
 * @status accepted
 * @rationale Co-locating fetch + update in a single hook keeps the
 *   CompanionSettings component thin and consistent with the notification
 *   preferences approach (DEC-NOTIF-012). Preferences are fetched eagerly
 *   (not lazily) because the companion settings page always needs them.
 *
 * @decision DEC-FRONTEND-079
 * @title Companion preferences fetch gated on isAuthenticated; no silent default fallback
 * @status accepted
 * @rationale Three symptoms converged on the same root cause: preferences
 *   were not persisting across page reload.
 *
 *   Root cause A (auth-race): the hook previously fired unconditionally on
 *   mount. If a caller passed isAuthenticated=false (e.g. a component rendered
 *   before auth settled), the fetch would fire without a valid token and
 *   receive a 401 → the catch block silently set DEFAULT_COMPANION_PREFERENCES,
 *   overwriting the user's saved values in local state for the lifetime of
 *   that component instance. Fix: accept optional isAuthenticated and skip
 *   the fetch when false; re-fire when it flips to true via the useEffect
 *   dependency array.
 *
 *   Root cause B (silent fallback): any error (transient 500, network blip)
 *   silently set DEFAULT_COMPANION_PREFERENCES, making the UI appear to have
 *   lost preferences when the underlying issue was transient. Fix: on error,
 *   leave preferences as null so the UI can display a retry state rather
 *   than silently reverting to hardcoded defaults. Callers that want to
 *   render something before preferences load should check `preferences ?? DEFAULT_COMPANION_PREFERENCES`.
 *
 *   The client.ts request() helper already handles 401 with a single
 *   refresh-token retry, so a genuinely expired token is recovered
 *   transparently. No additional retry logic is needed here.
 */

import { useCallback, useEffect, useState } from 'react'
import { getCompanionPreferences, updateCompanionPreferences } from '../api/client'
import type { CompanionPreferences } from '../types'

export const DEFAULT_COMPANION_PREFERENCES: CompanionPreferences = {
  name: 'Ada',
  voice: 'female',
  personality: {
    warmth: 'warm',
    verbosity: 'balanced',
    formality: 'casual',
  },
}

interface UseCompanionPreferencesResult {
  preferences: CompanionPreferences | null
  loading: boolean
  update: (prefs: Partial<CompanionPreferences>) => Promise<void>
}

/**
 * @param isAuthenticated - When provided, the fetch is deferred until this is
 *   true and re-fired whenever it transitions to true (e.g. on login). When
 *   omitted, the hook fires immediately on mount (backwards-compatible for
 *   components that are only ever rendered inside an authenticated tree).
 */
export function useCompanionPreferences(
  isAuthenticated?: boolean,
): UseCompanionPreferencesResult {
  const [preferences, setPreferences] = useState<CompanionPreferences | null>(null)
  const [loading, setLoading] = useState(true)

  // Gate: skip fetch when caller signals auth is not yet ready.
  // The effect re-fires when isAuthenticated flips from false → true.
  const shouldFetch = isAuthenticated === undefined || isAuthenticated === true

  useEffect(() => {
    if (!shouldFetch) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    getCompanionPreferences()
      .then((data) => {
        if (!cancelled) setPreferences(data)
      })
      .catch((err) => {
        // Do NOT silently fall back to DEFAULT_COMPANION_PREFERENCES here.
        // Doing so would overwrite the user's saved preferences in local state
        // on any transient error (DEC-FRONTEND-079). Leave preferences as null
        // so the UI can distinguish "not yet loaded" from "loaded with values".
        // Callers should render `preferences ?? DEFAULT_COMPANION_PREFERENCES`
        // as a display-only fallback without calling update() on it.
        console.error('Failed to load companion preferences:', err)
        if (!cancelled) setPreferences(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [shouldFetch])

  const update = useCallback(async (prefs: Partial<CompanionPreferences>) => {
    setLoading(true)
    try {
      const updated = await updateCompanionPreferences(prefs)
      setPreferences(updated)
    } catch (err) {
      console.error('Failed to update companion preferences:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  return { preferences, loading, update }
}
