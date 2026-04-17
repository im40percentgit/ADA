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
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import { ProgressBar } from './ui/ProgressBar'
import { Skeleton } from './ui/Skeleton'
import { ErrorState } from './ui/ErrorState'

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
      <div className="patient-dash" data-testid="screening-intro" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
        <Button
          variant="secondary"
          size="sm"
          onClick={onBack}
          className="med-card__btn"
        >
          Back
        </Button>

        <section aria-label="Screening introduction">
        <Card style={{ marginTop: 'var(--space-md)' }}>
          <h1 style={{ margin: '0 0 var(--space-sm)', fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h1)', fontWeight: 700 }}>
            Cognitive Screening
          </h1>
          <p style={{ margin: '0 0 var(--space-md)', lineHeight: 1.6, color: 'var(--color-text-secondary)' }}>
            This assessment takes about 8-10 minutes and covers memory, attention,
            language, and visuospatial skills. You will be shown a series of tasks
            to complete at your own pace.
          </p>

          {error && (
            <p className="patient-dash__error" role="alert" style={{ marginBottom: 'var(--space-md)', color: 'var(--color-danger)' }}>
              {error}
            </p>
          )}

          <button
            type="button"
            onClick={() => start(patientId)}
            data-testid="start-screening"
            style={{
              padding: 'var(--space-md) var(--space-xl)',
              borderRadius: 'var(--radius-button)',
              border: 'none',
              backgroundColor: 'var(--color-primary)',
              color: '#fff',
              fontWeight: 600,
              fontSize: 'var(--size-body)',
              fontFamily: 'var(--font-body)',
              cursor: 'pointer',
              minHeight: 'var(--touch-target-min)',
            }}
          >
            Start Screening
          </button>
        </Card>
        </section>
      </div>
    )
  }

  // -- Starting (loading) state ----------------------------------------------

  if (status === 'starting') {
    return (
      <div className="patient-dash" aria-busy="true" data-testid="screening-loading" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
        <Skeleton variant="block" height="200px" aria-label="Starting screening…" />
      </div>
    )
  }

  // -- Error state (can happen after start) ----------------------------------

  if (error && !currentTask) {
    return (
      <div className="patient-dash" style={{ fontFamily: 'var(--font-body)' }}>
        <ErrorState
          title="Could not start screening"
          message={error}
          action={<Button variant="secondary" onClick={onBack}>Go back</Button>}
        />
      </div>
    )
  }

  // -- In-progress: waiting for task -----------------------------------------

  if (status === 'in_progress' && !currentTask) {
    return (
      <div className="patient-dash" data-testid="screening-waiting" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
        <Skeleton variant="block" height="200px" aria-label="Waiting for next task…" />
      </div>
    )
  }

  // -- In-progress: task visible ---------------------------------------------

  if (status === 'in_progress' && currentTask) {
    const progressPct = totalTasks > 0 ? ((taskIndex) / totalTasks) * 100 : 0

    return (
      <div className="patient-dash" data-testid="screening-task" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
        <Button
          variant="secondary"
          size="sm"
          onClick={onBack}
          className="med-card__btn"
        >
          Back
        </Button>

        <section aria-label={`Task ${currentTask.task_index + 1} of ${totalTasks}: ${currentTask.domain}`}>
        <Card style={{ marginTop: 'var(--space-md)' }}>
          {/* Domain label + task counter */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 'var(--space-sm)',
            }}
          >
            <span
              data-testid="domain-label"
              style={{
                display: 'inline-block',
                padding: '2px 8px',
                borderRadius: '10px',
                backgroundColor: 'var(--color-primary-subtle)',
                color: 'var(--color-primary-light)',
                fontWeight: 600,
                fontSize: 'var(--size-xs)',
                textTransform: 'uppercase',
              }}
            >
              {currentTask.domain}
            </span>
            <span
              data-testid="task-counter"
              style={{ fontSize: 'var(--size-sm)', color: 'var(--color-text-muted)', fontWeight: 500 }}
            >
              Task {currentTask.task_index + 1} of {totalTasks}
            </span>
          </div>

          {/* Progress bar */}
          <div style={{ marginBottom: 'var(--space-lg)' }}>
            <ProgressBar value={progressPct} />
          </div>

          {/* Task prompt */}
          <p
            style={{
              margin: '0 0 var(--space-md)',
              fontSize: 'var(--size-h2)',
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
        </Card>
        </section>
      </div>
    )
  }

  // -- Completed (brief display before onComplete fires) ---------------------

  return (
    <div className="patient-dash" data-testid="screening-complete" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
      <p>Screening complete.</p>
    </div>
  )
}
