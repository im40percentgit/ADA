/**
 * @file useCircles.ts
 * @description React hook for loading and selecting Care Circles.
 *   Fetches the authenticated user's circles from GET /api/circles/my,
 *   auto-selects the first circle on load, and exposes a refresh function
 *   for manual refetch after mutations.
 * @rationale Centralising circle fetch + selection state in a hook keeps
 *   CaregiverDashboard lean and allows any future consumer (e.g. a mobile
 *   nav bar) to share the same selection without prop-drilling. The hook
 *   intentionally does NOT auto-refresh on an interval — circle membership
 *   changes infrequently and the dashboard will re-mount after navigation.
 *
 * @decision DEC-FRONTEND-030
 * @title useCircles auto-selects first circle, no polling
 * @status accepted
 * @rationale Care circles change infrequently (invites, not live data).
 *   A single fetch on mount with manual refresh is sufficient. Auto-selection
 *   of the first circle gives single-patient caregivers a zero-click experience
 *   while multi-patient caregivers can override via CircleSelector.
 */

import { useCallback, useEffect, useState } from 'react'

import { getMyCircles } from '../api/client'
import type { CareCircle } from '../types'

interface UseCirclesResult {
  circles: CareCircle[]
  selectedCircle: CareCircle | null
  selectCircle: (circle: CareCircle) => void
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useCircles(): UseCirclesResult {
  const [circles, setCircles] = useState<CareCircle[]>([])
  const [selectedCircle, setSelectedCircle] = useState<CareCircle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getMyCircles()
      setCircles(data)
      if (data.length > 0 && !selectedCircle) {
        setSelectedCircle(data[0])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load circles')
    } finally {
      setLoading(false)
    }
  }, [selectedCircle])

  useEffect(() => {
    refresh()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const selectCircle = useCallback((circle: CareCircle) => {
    setSelectedCircle(circle)
  }, [])

  return { circles, selectedCircle, selectCircle, loading, error, refresh }
}
