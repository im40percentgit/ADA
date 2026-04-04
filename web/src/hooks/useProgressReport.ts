/**
 * useProgressReport — fetches progress report data for a patient.
 *
 * Wraps getProgressReport(patientId, range) from client.ts.
 * State: data, loading, error, range (default '2w'), setRange.
 * Re-fetches automatically when range changes via useEffect.
 *
 * @decision DEC-FRONTEND-050
 * @title useProgressReport hook manages range state and re-fetch
 * @status accepted
 * @rationale Co-locating the range selector state with the fetch logic
 *   keeps ProgressReport.tsx focused on layout/rendering. The hook
 *   follows the same cancelled-flag pattern used by MoodChart and other
 *   data hooks in this codebase.
 */

import { useState, useEffect } from 'react'
import { getProgressReport } from '../api/client'
import type { ProgressReportData } from '../types'

export type TimeRange = '1w' | '2w' | '1m' | '3m' | 'all'

export function useProgressReport(patientId: string) {
  const [data, setData] = useState<ProgressReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [range, setRange] = useState<TimeRange>('2w')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    getProgressReport(patientId, range)
      .then((report) => {
        if (!cancelled) setData(report)
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load progress report')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [patientId, range])

  return { data, loading, error, range, setRange }
}
