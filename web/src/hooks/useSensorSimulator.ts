/**
 * useSensorSimulator — REST hook for controlling the backend sensor simulator.
 *
 * Wraps the POST /api/sessions/{sid}/simulator/start and
 * POST /api/sessions/{sid}/simulator/stop endpoints. The simulator
 * generates SENSOR_READING events server-side; those events are forwarded
 * to the chat WebSocket as vitals_update messages by the chat endpoint.
 *
 * @decision DEC-FRONTEND-012
 * @title useSensorSimulator uses direct fetch rather than the shared request() helper
 * @status accepted
 * @rationale The shared request() helper in client.ts is typed around domain
 *   entities (Patient, Session, Assessment). Simulator endpoints return
 *   ad-hoc status objects with no shared type. Using fetch directly avoids
 *   casting through unknown and keeps the hook self-contained. The 401 retry
 *   logic is not needed here — simulator start/stop is a dev-time tool and
 *   a stale token error can be surfaced to the user as-is.
 */

import { useState, useCallback } from 'react'
import { getAccessToken } from '../api/auth'

export type SimulatorPreset = 'relaxed' | 'anxious' | 'panic_attack'

export interface UseSensorSimulatorReturn {
  running: boolean
  start: (preset: SimulatorPreset, patientId?: string, durationS?: number) => Promise<void>
  stop: () => Promise<void>
  error: string | null
}

export function useSensorSimulator(sessionId: string): UseSensorSimulatorReturn {
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const authHeaders = useCallback((): Record<string, string> => {
    const token = getAccessToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  }, [])

  const start = useCallback(
    async (preset: SimulatorPreset, patientId = '', durationS = 120) => {
      setError(null)
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/simulator/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({ preset, patient_id: patientId, duration_s: durationS }),
        })
        if (!res.ok) {
          const text = await res.text().catch(() => res.statusText)
          throw new Error(`${res.status}: ${text}`)
        }
        setRunning(true)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setError(`Failed to start simulator: ${msg}`)
      }
    },
    [sessionId, authHeaders],
  )

  const stop = useCallback(async () => {
    setError(null)
    try {
      const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/simulator/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
      })
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText)
        throw new Error(`${res.status}: ${text}`)
      }
      setRunning(false)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(`Failed to stop simulator: ${msg}`)
    }
  }, [sessionId, authHeaders])

  return { running, start, stop, error }
}
