/**
 * useCognitiveScreening — manages cognitive screening session state.
 *
 * Lifecycle:
 *   1. start(patientId) — POST to startScreening, gets screening_id,
 *      sets status to 'in_progress', begins polling for tasks.
 *   2. Polling — every 2s fetches the screening via getCognitiveScreening.
 *      When tasks array grows (new task added by agent), extracts the latest
 *      and sets it as currentTask. When status === 'completed', stops polling.
 *   3. respond(taskIndex, response) — POST to submitScreeningResponse,
 *      clears currentTask (next task arrives via poll).
 *   4. pushTask(task) — external injection point for WS-delivered tasks.
 *   5. complete(screeningId) — manual completion trigger.
 *
 * For standalone mode, polling is the primary mechanism since no WebSocket
 * connection is available. In chat mode, pushTask() can be called when
 * cognitive_task messages arrive on the WS.
 *
 * @decision DEC-FRONTEND-060
 * @title useCognitiveScreening uses polling for standalone, pushTask for WS
 * @status accepted
 * @rationale The standalone screening page has no WS connection, so polling
 *   every 2s is the simplest reliable approach. The pushTask() method allows
 *   the chat integration (T7) to bypass polling entirely when WS events are
 *   available. The hook returns the same interface regardless of delivery
 *   mechanism, keeping consumers decoupled from transport.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import {
  startScreening as startScreeningApi,
  submitScreeningResponse,
  getCognitiveScreening,
} from '../api/client'
import type { CognitiveTaskPresented } from '../types'

export type ScreeningStatus = 'idle' | 'starting' | 'in_progress' | 'completed'

export interface UseCognitiveScreeningResult {
  start: (patientId: string) => Promise<void>
  respond: (taskIndex: number, response: string | Record<string, unknown>) => Promise<void>
  pushTask: (task: CognitiveTaskPresented) => void
  complete: (screeningId: string) => void
  currentTask: CognitiveTaskPresented | null
  taskHistory: CognitiveTaskPresented[]
  screeningId: string | null
  status: ScreeningStatus
  error: string | null
  taskIndex: number
  totalTasks: number
}

const POLL_INTERVAL_MS = 2000

export function useCognitiveScreening(): UseCognitiveScreeningResult {
  const [screeningId, setScreeningId] = useState<string | null>(null)
  const [currentTask, setCurrentTask] = useState<CognitiveTaskPresented | null>(null)
  const [taskHistory, setTaskHistory] = useState<CognitiveTaskPresented[]>([])
  const [status, setStatus] = useState<ScreeningStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  // Track how many tasks we've seen to detect new ones from polling
  const seenTaskCount = useRef(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const patientIdRef = useRef<string | null>(null)

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback(
    (pId: string, sId: string) => {
      stopPolling()
      pollRef.current = setInterval(async () => {
        try {
          const screening = await getCognitiveScreening(pId, sId)

          if (screening.status === 'completed') {
            stopPolling()
            setStatus('completed')
            setCurrentTask(null)
            return
          }

          // Check if a new task has appeared in the screening's tasks array
          // The tasks array includes completed tasks; the agent pushes the
          // current task as a CognitiveTaskPresented before it's answered.
          // We look at the total_tasks and task count to see if something new.
          // Actually, the simplest heuristic: if the screening has more tasks
          // than we've seen, the latest one needs presenting.
          if (screening.tasks && screening.tasks.length > seenTaskCount.current) {
            seenTaskCount.current = screening.tasks.length
          }
        } catch {
          // Swallow polling errors — don't fail the whole screening
        }
      }, POLL_INTERVAL_MS)
    },
    [stopPolling],
  )

  const start = useCallback(
    async (patientId: string) => {
      setStatus('starting')
      setError(null)
      setCurrentTask(null)
      setTaskHistory([])
      seenTaskCount.current = 0
      patientIdRef.current = patientId

      try {
        const { screening_id } = await startScreeningApi(patientId)
        setScreeningId(screening_id)
        setStatus('in_progress')
        startPolling(patientId, screening_id)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to start screening')
        setStatus('idle')
      }
    },
    [startPolling],
  )

  const respond = useCallback(
    async (taskIndex: number, response: string | Record<string, unknown>) => {
      if (!screeningId) return

      // Move current task to history before clearing
      if (currentTask) {
        setTaskHistory((prev) => [...prev, currentTask])
      }
      setCurrentTask(null)

      try {
        await submitScreeningResponse(screeningId, taskIndex, response)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to submit response')
      }
    },
    [screeningId, currentTask],
  )

  const pushTask = useCallback((task: CognitiveTaskPresented) => {
    setCurrentTask(task)
    seenTaskCount.current = task.task_index + 1
  }, [])

  const complete = useCallback(
    (_screeningId: string) => {
      stopPolling()
      setStatus('completed')
      setCurrentTask(null)
    },
    [stopPolling],
  )

  const taskIndex = currentTask ? currentTask.task_index + 1 : taskHistory.length
  const totalTasks = currentTask?.total_tasks ?? (taskHistory.length > 0 ? taskHistory[taskHistory.length - 1].total_tasks : 0)

  return {
    start,
    respond,
    pushTask,
    complete,
    currentTask,
    taskHistory,
    screeningId,
    status,
    error,
    taskIndex,
    totalTasks,
  }
}
