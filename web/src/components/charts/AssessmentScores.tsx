/**
 * AssessmentScores — three-card row showing PHQ-9, GAD-7, WHO-5 scores.
 *
 * Each card displays: instrument name, current score, severity label,
 * and trend arrow with delta vs previous. Handles missing instruments
 * gracefully.
 *
 * @decision DEC-FRONTEND-055
 * @title AssessmentScores renders cards inline rather than as separate components
 * @status accepted
 * @rationale Each card is ~10 lines of JSX. Three tiny card components
 *   would add file overhead without improving readability. A single
 *   component with a map keeps the logic co-located.
 */

interface ScoreEntry {
  current: number
  previous: number | null
  severity: string
}

interface AssessmentScoresProps {
  data: Record<string, ScoreEntry>
}

const INSTRUMENTS = ['phq9', 'gad7', 'who5']

const LABELS: Record<string, string> = {
  phq9: 'PHQ-9',
  gad7: 'GAD-7',
  who5: 'WHO-5',
}

function trendArrow(current: number, previous: number | null, instrument: string): string {
  if (previous === null) return ''
  const delta = current - previous
  if (delta === 0) return ' \u2192 0'
  // For WHO-5, higher is better. For PHQ-9/GAD-7, lower is better.
  if (instrument === 'who5') {
    return delta > 0 ? ` \u2191 +${delta}` : ` \u2193 ${delta}`
  }
  return delta < 0 ? ` \u2191 ${delta}` : ` \u2193 +${delta}`
}

function trendColor(current: number, previous: number | null, instrument: string): string {
  if (previous === null) return '#6b7280'
  const delta = current - previous
  if (delta === 0) return '#6b7280'
  // For WHO-5, positive delta is good. For PHQ-9/GAD-7, negative delta is good.
  if (instrument === 'who5') {
    return delta > 0 ? '#059669' : '#dc2626'
  }
  return delta < 0 ? '#059669' : '#dc2626'
}

export function AssessmentScores({ data }: AssessmentScoresProps) {
  const available = INSTRUMENTS.filter((key) => key in data)

  if (available.length === 0) {
    return <p className="patient-dash__empty">No assessment scores available</p>
  }

  return (
    <section aria-label="Assessment scores">
      <h4>Assessment Scores</h4>
      <div style={{ display: 'flex', gap: '12px', marginTop: '8px', flexWrap: 'wrap' }}>
        {available.map((key) => {
          const entry = data[key]
          return (
            <div
              key={key}
              style={{
                flex: '1 1 140px',
                padding: '12px',
                borderRadius: '8px',
                background: '#f9fafb',
                border: '1px solid #e5e7eb',
                minWidth: '120px',
              }}
            >
              <p style={{ margin: 0, fontSize: '12px', color: '#6b7280', fontWeight: 600 }}>
                {LABELS[key] ?? key}
              </p>
              <p style={{ margin: '4px 0', fontSize: '24px', fontWeight: 700, color: '#111827' }}>
                {entry.current}
              </p>
              <p style={{ margin: 0, fontSize: '13px', color: '#6b7280' }}>
                {entry.severity}
              </p>
              <p
                style={{
                  margin: '4px 0 0',
                  fontSize: '13px',
                  fontWeight: 500,
                  color: trendColor(entry.current, entry.previous, key),
                }}
              >
                {trendArrow(entry.current, entry.previous, key)}
              </p>
            </div>
          )
        })}
      </div>
    </section>
  )
}
