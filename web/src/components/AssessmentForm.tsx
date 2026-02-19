/**
 * AssessmentForm — interactive PHQ-9 / GAD-7 questionnaire
 *
 * Renders all questions with a 0-3 Likert scale, shows a running total,
 * and submits scores to /api/assessments. Displays severity interpretation
 * on completion.
 *
 * @decision DEC-FRONTEND-006
 * @title AssessmentForm uses controlled radio inputs with running total
 * @status accepted
 * @rationale Controlled inputs give React full ownership of form state,
 *   making the running total trivial to compute without refs or DOM queries.
 *   Severity thresholds are encoded here (matching the backend scoring module)
 *   so the user sees immediate feedback before the API response arrives.
 */

import { useState } from 'react'
import { submitAssessment } from '../api/client'
import {
  PHQ9_QUESTIONS,
  GAD7_QUESTIONS,
  SCORE_LABELS,
  type AssessmentInstrument,
  type Assessment,
} from '../types'

interface AssessmentFormProps {
  instrument: AssessmentInstrument
  patientId: string
  sessionId: string | null
  onComplete: (result: Assessment) => void
  onDismiss: () => void
}

// Severity thresholds mirror ada/assessment/ scoring module
const PHQ9_SEVERITY = (score: number) => {
  if (score <= 4) return 'Minimal depression'
  if (score <= 9) return 'Mild depression'
  if (score <= 14) return 'Moderate depression'
  if (score <= 19) return 'Moderately severe depression'
  return 'Severe depression'
}

const GAD7_SEVERITY = (score: number) => {
  if (score <= 4) return 'Minimal anxiety'
  if (score <= 9) return 'Mild anxiety'
  if (score <= 14) return 'Moderate anxiety'
  return 'Severe anxiety'
}

export function AssessmentForm({
  instrument,
  patientId,
  sessionId,
  onComplete,
  onDismiss,
}: AssessmentFormProps) {
  const questions = instrument === 'phq9' ? PHQ9_QUESTIONS : GAD7_QUESTIONS
  const title = instrument === 'phq9' ? 'PHQ-9 Depression Scale' : 'GAD-7 Anxiety Scale'

  const [scores, setScores] = useState<(number | null)[]>(
    Array(questions.length).fill(null),
  )
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<Assessment | null>(null)
  const [error, setError] = useState<string | null>(null)

  const answered = scores.filter((s) => s !== null).length
  const total = scores.reduce<number>((sum, s) => sum + (s ?? 0), 0)
  const allAnswered = answered === questions.length

  const severity =
    result != null
      ? result.severity
      : instrument === 'phq9'
        ? PHQ9_SEVERITY(total)
        : GAD7_SEVERITY(total)

  function handleScore(questionIndex: number, value: number) {
    setScores((prev) => {
      const next = [...prev]
      next[questionIndex] = value
      return next
    })
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!allAnswered) return

    setSubmitting(true)
    setError(null)

    try {
      const assessment = await submitAssessment({
        patient_id: patientId,
        session_id: sessionId,
        instrument,
        scores: scores as number[],
      })
      setResult(assessment)
      onComplete(assessment)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  if (result) {
    return (
      <div className="assessment-form assessment-form--complete" role="region" aria-label="Assessment results">
        <h2 className="assessment-form__title">{title} — Results</h2>
        <div className="assessment-form__result">
          <div className="assessment-form__score-display">
            <span className="assessment-form__score-value">{result.total_score}</span>
            <span className="assessment-form__score-label">/ {questions.length * 3}</span>
          </div>
          <p className="assessment-form__severity">{severity}</p>
          <p className="assessment-form__note">
            These results have been saved and shared with your care team.
          </p>
        </div>
        <button
          className="assessment-form__btn assessment-form__btn--primary"
          onClick={onDismiss}
          type="button"
        >
          Continue
        </button>
      </div>
    )
  }

  return (
    <div className="assessment-form" role="region" aria-label={title}>
      <div className="assessment-form__header">
        <h2 className="assessment-form__title">{title}</h2>
        <p className="assessment-form__instruction">
          Over the <strong>last 2 weeks</strong>, how often have you been bothered by the following?
        </p>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <ol className="assessment-form__questions">
          {questions.map((q) => (
            <li key={q.index} className="assessment-form__question">
              <fieldset>
                <legend className="assessment-form__question-text">
                  {q.index + 1}. {q.text}
                </legend>
                <div className="assessment-form__options" role="group">
                  {SCORE_LABELS.map((label, value) => {
                    const inputId = `${instrument}-q${q.index}-v${value}`
                    return (
                      <label key={value} htmlFor={inputId} className="assessment-form__option">
                        <input
                          id={inputId}
                          type="radio"
                          name={`${instrument}-q${q.index}`}
                          value={value}
                          checked={scores[q.index] === value}
                          onChange={() => handleScore(q.index, value)}
                          className="assessment-form__radio"
                        />
                        <span className="assessment-form__option-label">{label}</span>
                        <span className="assessment-form__option-value">{value}</span>
                      </label>
                    )
                  })}
                </div>
              </fieldset>
            </li>
          ))}
        </ol>

        <div className="assessment-form__footer">
          <div className="assessment-form__running-total" aria-live="polite">
            {answered > 0 && (
              <>
                <span className="assessment-form__total-label">Running total:</span>
                <span className="assessment-form__total-value">{total}</span>
                <span className="assessment-form__total-progress">
                  ({answered} of {questions.length} answered)
                </span>
              </>
            )}
          </div>

          {error && (
            <p className="assessment-form__error" role="alert">
              {error}
            </p>
          )}

          <div className="assessment-form__actions">
            <button
              type="button"
              className="assessment-form__btn assessment-form__btn--secondary"
              onClick={onDismiss}
              disabled={submitting}
            >
              Skip for now
            </button>
            <button
              type="submit"
              className="assessment-form__btn assessment-form__btn--primary"
              disabled={!allAnswered || submitting}
              aria-describedby={!allAnswered ? 'assessment-incomplete-hint' : undefined}
            >
              {submitting ? 'Submitting…' : 'Submit'}
            </button>
          </div>
          {!allAnswered && (
            <p id="assessment-incomplete-hint" className="assessment-form__hint">
              Please answer all {questions.length} questions to submit.
            </p>
          )}
        </div>
      </form>
    </div>
  )
}
