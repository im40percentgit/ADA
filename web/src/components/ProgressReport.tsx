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
 *
 * @decision DEC-CLIN-STATES-001
 * @title AsyncBoundary pattern: SkeletonCard for initial load, isFetching skeleton for range switch
 * @status accepted
 * @rationale On initial load (loading=true, no data), a SkeletonCard fills the chart area.
 *   On range-change re-fetches (isFetching=true, data already present), the chart grid is
 *   replaced with a Skeleton(block) so the user sees immediate feedback rather than stale
 *   charts with an invisible loader overlay. DEC-MOTION-007 (.chart-tooltip-motion wrappers
 *   on WellbeingTrendChart and SessionFrequencyChart) are only rendered when isFetching is
 *   false — the skeleton replaces the chart container entirely during the fetch window.
 *   ErrorState replaces the inline danger-text pattern. EmptyState (tone="info") replaces
 *   the plain "No progress data available" paragraph.
 */

import { useProgressReport, type TimeRange } from '../hooks/useProgressReport'
import { usePdfExport } from '../hooks/usePdfExport'
import { WellbeingTrendChart } from './charts/WellbeingTrendChart'
import { SessionFrequencyChart } from './charts/SessionFrequencyChart'
import { EmotionDistribution } from './charts/EmotionDistribution'
import { AdherenceDonut } from './charts/AdherenceDonut'
import { AssessmentScores } from './charts/AssessmentScores'
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import { Skeleton, SkeletonCard } from './ui/Skeleton'
import { EmptyState } from './ui/EmptyState'
import { ErrorState } from './ui/ErrorState'

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
  const { data, loading, isFetching, error, range, setRange } = useProgressReport(patientId)
  const { exportToPdf, exporting } = usePdfExport()

  if (loading) {
    return (
      <div className="patient-dash" aria-busy="true" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
        <SkeletonCard lines={4} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="patient-dash" style={{ fontFamily: 'var(--font-body)' }}>
        <ErrorState
          title="Could not load progress report"
          message={error}
          action={<Button variant="secondary" onClick={onBack}>Go back</Button>}
        />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="patient-dash" style={{ fontFamily: 'var(--font-body)' }}>
        <EmptyState
          icon="📊"
          title="Nothing to report yet"
          description="Check back after your first session."
          tone="info"
          action={<Button variant="secondary" onClick={onBack}>Go back</Button>}
        />
      </div>
    )
  }

  return (
    <div className="patient-dash" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
      {/* Back button + PDF export */}
      <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'center' }}>
        <Button
          variant="secondary"
          size="sm"
          onClick={onBack}
          className="med-card__btn"
        >
          Back
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => exportToPdf('export-progress-report', `progress-report-${range}.pdf`)}
          disabled={exporting}
        >
          {exporting ? 'Exporting...' : 'Download PDF'}
        </Button>
      </div>

      <div id="export-progress-report">
      <h1 className="sr-only">Progress Report</h1>

      {/* Time range pills */}
      <div
        style={{ display: 'flex', gap: 'var(--space-sm)', marginBottom: 'var(--space-md)', marginTop: 'var(--space-md)', flexWrap: 'wrap' }}
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
              borderRadius: 'var(--radius-card)',
              fontSize: 'var(--size-caption)',
              fontWeight: 600,
              cursor: 'pointer',
              background: range === r.value ? 'var(--color-primary)' : 'var(--color-bg-elevated)',
              color: range === r.value ? '#fff' : 'var(--color-text-muted)',
              border: 'none',
            }}
            aria-pressed={range === r.value}
          >
            {r.label}
          </span>
        ))}
      </div>

      {/* AI Narrative card — warmth tint */}
      <section aria-label="AI Narrative">
      <Card style={{ borderLeft: '4px solid var(--color-warmth)', paddingLeft: 'var(--space-md)' }}>
        <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-sm)' }}>AI Narrative</h2>
        <p style={{ margin: 0, lineHeight: 1.6, color: 'var(--color-text-secondary)' }}>{data.narrative}</p>
      </Card>
      </section>

      {/* 2x2 chart grid — replaced by skeleton while range-change fetch is in flight */}
      {isFetching ? (
        <Skeleton
          variant="block"
          height="320px"
          style={{ marginTop: 'var(--space-md)' }}
          aria-label="Loading chart data…"
        />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 'var(--space-md)',
            marginTop: 'var(--space-md)',
          }}
        >
          <section aria-label="WHO-5 Wellbeing Trend">
            <Card>
              <WellbeingTrendChart data={data.who5_trend} />
            </Card>
          </section>
          <section aria-label="Session Frequency">
            <Card>
              <SessionFrequencyChart data={data.session_count_by_week} />
            </Card>
          </section>
          <section aria-label="Emotion Distribution">
            <Card>
              <EmotionDistribution data={data.emotion_distribution} />
            </Card>
          </section>
          <section aria-label="Medication Adherence">
            <Card>
              <AdherenceDonut data={data.medication_adherence} />
            </Card>
          </section>
        </div>
      )}

      {/* Assessment Scores */}
      <section aria-label="Assessment Scores">
      <Card style={{ marginTop: 'var(--space-md)' }}>
        <AssessmentScores data={data.assessment_scores} />
      </Card>
      </section>
      </div>
    </div>
  )
}
