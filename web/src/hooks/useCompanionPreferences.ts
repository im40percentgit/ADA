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

export function useCompanionPreferences(): UseCompanionPreferencesResult {
  const [preferences, setPreferences] = useState<CompanionPreferences | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getCompanionPreferences()
      .then((data) => {
        if (!cancelled) setPreferences(data)
      })
      .catch(() => {
        // Fall back to defaults on error so the UI is never empty
        if (!cancelled) setPreferences(DEFAULT_COMPANION_PREFERENCES)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

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
