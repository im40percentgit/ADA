/**
 * CognitiveScreening — standalone screening page with step-by-step flow.
 *
 * Three states:
 *   1. Intro — title, description, Start button
 *   2. In-progress — domain label, task counter, progress bar, ScreeningTask
 *   3. Completed — triggers onComplete callback
 *
 * Uses useCognitiveScreening hook for state management. In standalone mode,
 * polling delivers new tasks after each response. In chat mode (T7),
 * pushTask() is called by the parent when WS events arrive.
 *
 * @decision DEC-FRONTEND-062
 * @title CognitiveScreening page manages intro/task/complete states
 * @status accepted
 * @rationale The three-state flow matches the user journey: introduction with
 *   consent → sequential task presentation → completion handoff. The progress
 *   bar and domain labels provide context during what can be a 8-10 minute
 *   assessment. The onComplete callback lets the parent navigate to results.
 */

import { useEffect, useRef } from 'react'
import { useCognitiveScreening } from '../hooks/useCognitiveScreening'
import { ScreeningTask } from './ScreeningTask'

interface CognitiveScreeningProps {
  patientId: string
  onBack: () => void
  onComplete: (screeningId: string) => void
}

export function CognitiveScreening({
  patientId,
  onBack,
  onComplete,
}: CognitiveScreeningProps) {
  const {
    start,
    respond,
    currentTask,
    screeningId,
    status,
    error,
    taskIndex,
    totalTasks,
  } = useCognitiveScreening()

  // Track whether we've already fired onComplete to avoid double-calling
  const completedRef = useRef(false)

  useEffect(() => {
    if (status === 'completed' && screeningId && !completedRef.current) {
      completedRef.current = true
      onComplete(screeningId)
    }
  }, [status, screeningId, onComplete])

  // -- Intro screen ----------------------------------------------------------

  if (status === 'idle') {
    return (
      <div className="patient-dash" data-testid="screening-intro">
        <button
          type="button"
          className="med-card__btn med-card__btn--secondary"
          onClick={onBack}
          style={{ alignSelf: 'flex-start', marginBottom: '12px' }}
        >
          Back
        </button>

        <h2 style={{ margin: '0 0 8px', fontSize: '1.5rem', fontWeight: 700 }}>
          Cognitive Screening
        </h2>
        <p style={{ margin: '0 0 16px', lineHeight: 1.6, color: '#4b5563' }}>
          This assessment takes about 8-10 minutes and covers memory, attention,
          language, and visuospatial skills. You will be shown a series of tasks
          to complete at your own pace.
        </p>

        {error && (
          <p className="patient-dash__error" role="alert" style={{ marginBottom: '12px' }}>
            {error}
          </p>
        )}

        <button
          type="button"
          onClick={() => start(patientId)}
          data-testid="start-screening"
          style={{
            padding: '12px 32px',
            borderRadius: '8px',
            border: 'none',
            backgroundColor: '#3b82f6',
            color: '#fff',
            fontWeight: 600,
            fontSize: '1rem',
            cursor: 'pointer',
          }}
        >
          Start Screening
        </button>
      </div>
    )
  }

  // -- Starting (loading) state ----------------------------------------------

  if (status === 'starting') {
    return (
      <div className="patient-dash" aria-busy="true" data-testid="screening-loading">
        <p>Starting screening...</p>
      </div>
    )
  }

  // -- Error state (can happen after start) ----------------------------------

  if (error && !currentTask) {
    return (
      <div className="patient-dash" role="alert">
        <p className="patient-dash__error">{error}</p>
        <button
          type="button"
          className="med-card__btn med-card__btn--secondary"
          onClick={onBack}
        >
          Back
        </button>
      </div>
    )
  }

  // -- In-progress: waiting for task -----------------------------------------

  if (status === 'in_progress' && !currentTask) {
    return (
      <div className="patient-dash" data-testid="screening-waiting">
        <p>Waiting for next task...</p>
      </div>
    )
  }

  // -- In-progress: task visible ---------------------------------------------

  if (status === 'in_progress' && currentTask) {
    const progressPct = totalTasks > 0 ? ((taskIndex) / totalTasks) * 100 : 0

    return (
      <div className="patient-dash" data-testid="screening-task">
        <button
          type="button"
          className="med-card__btn med-card__btn--secondary"
          onClick={onBack}
          style={{ alignSelf: 'flex-start', marginBottom: '12px' }}
        >
          Back
        </button>

        {/* Domain label + task counter */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '8px',
          }}
        >
          <span
            data-testid="domain-label"
            style={{
              display: 'inline-block',
              padding: '4px 12px',
              borderRadius: '12px',
              backgroundColor: '#ede9fe',
              color: '#5b21b6',
              fontWeight: 600,
              fontSize: '0.85rem',
              textTransform: 'uppercase',
            }}
          >
            {currentTask.domain}
          </span>
          <span
            data-testid="task-counter"
            style={{ fontSize: '0.9rem', color: '#6b7280', fontWeight: 500 }}
          >
            Task {currentTask.task_index + 1} of {totalTasks}
          </span>
        </div>

        {/* Progress bar */}
        <div
          role="progressbar"
          aria-valuenow={Math.round(progressPct)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Screening progress"
          style={{
            height: '6px',
            backgroundColor: '#e5e7eb',
            borderRadius: '3px',
            marginBottom: '20px',
            overflow: 'hidden',
          }}
        >
          <div
            data-testid="progress-fill"
            style={{
              width: `${progressPct}%`,
              height: '100%',
              backgroundColor: '#3b82f6',
              borderRadius: '3px',
              transition: 'width 0.3s ease',
            }}
          />
        </div>

        {/* Task prompt */}
        <p
          style={{
            margin: '0 0 16px',
            fontSize: '1.1rem',
            fontWeight: 500,
            lineHeight: 1.5,
          }}
        >
          {currentTask.prompt}
        </p>

        {/* Task component */}
        <ScreeningTask
          task={currentTask}
          onSubmit={(response) => respond(currentTask.task_index, response)}
        />
      </div>
    )
  }

  // -- Completed (brief display before onComplete fires) ---------------------

  return (
    <div className="patient-dash" data-testid="screening-complete">
      <p>Screening complete.</p>
    </div>
  )
}
