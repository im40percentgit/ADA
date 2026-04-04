/**
 * ProgressReport — assembles the progress dashboard page.
 *
 * Layout:
 *   - Time range pills at top (1W/2W/1M/3M/ALL)
 *   - AI narrative card with blue left border
 *   - 2x2 grid of chart components
 *   - AssessmentScores section below
 *   - Back button
 *
 * All data is fetched via useProgressReport hook which manages range state
 * and re-fetches when the user switches time periods.
 *
 * @decision DEC-FRONTEND-056
 * @title ProgressReport assembles charts — does not fetch data itself
 * @status accepted
 * @rationale The useProgressReport hook owns the fetch + range state.
 *   ProgressReport is a pure layout component that receives data from
 *   the hook and passes slices to each chart. This separation makes both
 *   the hook and the layout independently testable.
 */

import { useProgressReport, type TimeRange } from '../hooks/useProgressReport'
import { WellbeingTrendChart } from './charts/WellbeingTrendChart'
import { SessionFrequencyChart } from './charts/SessionFrequencyChart'
import { EmotionDistribution } from './charts/EmotionDistribution'
import { AdherenceDonut } from './charts/AdherenceDonut'
import { AssessmentScores } from './charts/AssessmentScores'

interface ProgressReportProps {
  patientId: string
  onBack: () => void
}

const RANGES: { label: string; value: TimeRange }[] = [
  { label: '1W', value: '1w' },
  { label: '2W', value: '2w' },
  { label: '1M', value: '1m' },
  { label: '3M', value: '3m' },
  { label: 'ALL', value: 'all' },
]

export function ProgressReport({ patientId, onBack }: ProgressReportProps) {
  const { data, loading, error, range, setRange } = useProgressReport(patientId)

  if (loading) {
    return (
      <div className="patient-dash" aria-busy="true">
        Loading progress report...
      </div>
    )
  }

  if (error) {
    return (
      <div className="patient-dash" role="alert">
        <p className="patient-dash__error">{error}</p>
        <button type="button" className="med-card__btn med-card__btn--secondary" onClick={onBack}>
          Back
        </button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="patient-dash">
        <p className="patient-dash__empty">No progress data available</p>
        <button type="button" className="med-card__btn med-card__btn--secondary" onClick={onBack}>
          Back
        </button>
      </div>
    )
  }

  return (
    <div className="patient-dash">
      {/* Back button */}
      <button
        type="button"
        className="med-card__btn med-card__btn--secondary"
        onClick={onBack}
        style={{ alignSelf: 'flex-start', marginBottom: '12px' }}
      >
        Back
      </button>

      {/* Time range pills */}
      <div
        style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}
        role="group"
        aria-label="Time range selector"
      >
        {RANGES.map((r) => (
          <span
            key={r.value}
            role="button"
            tabIndex={0}
            onClick={() => setRange(r.value)}
            onKeyDown={(e) => e.key === 'Enter' && setRange(r.value)}
            style={{
              padding: '6px 14px',
              borderRadius: '16px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              background: range === r.value ? '#6366f1' : '#f3f4f6',
              color: range === r.value ? '#fff' : '#374151',
              border: 'none',
            }}
            aria-pressed={range === r.value}
          >
            {r.label}
          </span>
        ))}
      </div>

      {/* AI Narrative card */}
      <div
        className="patient-dash__card patient-dash__card--full"
        style={{ borderLeft: '4px solid #3b82f6', paddingLeft: '16px' }}
      >
        <h3>AI Narrative</h3>
        <p style={{ margin: 0, lineHeight: 1.6 }}>{data.narrative}</p>
      </div>

      {/* 2x2 chart grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '16px',
          marginTop: '16px',
        }}
      >
        <div className="patient-dash__card">
          <WellbeingTrendChart data={data.who5_trend} />
        </div>
        <div className="patient-dash__card">
          <SessionFrequencyChart data={data.session_count_by_week} />
        </div>
        <div className="patient-dash__card">
          <EmotionDistribution data={data.emotion_distribution} />
        </div>
        <div className="patient-dash__card">
          <AdherenceDonut data={data.medication_adherence} />
        </div>
      </div>

      {/* Assessment Scores */}
      <div className="patient-dash__card patient-dash__card--full" style={{ marginTop: '16px' }}>
        <AssessmentScores data={data.assessment_scores} />
      </div>
    </div>
  )
}
