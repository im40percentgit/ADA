/**
 * EmotionDistribution — colored chip display of emotion percentages.
 *
 * No chart library — renders colored span tag chips. Each emotion gets
 * a color from the EMOTION_COLORS map. Shows percentage next to the label.
 *
 * @decision DEC-FRONTEND-053
 * @title EmotionDistribution uses inline chips rather than a pie chart
 * @status accepted
 * @rationale Emotion distributions are categorical with few categories
 *   (typically 3-6). Colored chips with percentages are more scannable
 *   than pie chart wedges and avoid the readability problems of small
 *   arc segments.
 */

interface EmotionDistributionProps {
  data: Record<string, number>
}

const EMOTION_COLORS: Record<string, string> = {
  happy: '#22c55e',
  sad: '#3b82f6',
  angry: '#ef4444',
  anxious: '#f59e0b',
  neutral: '#9ca3af',
  calm: '#06b6d4',
  fearful: '#a855f7',
  disgusted: '#84cc16',
  surprised: '#f97316',
}

function getColor(emotion: string): string {
  return EMOTION_COLORS[emotion.toLowerCase()] ?? '#6b7280'
}

export function EmotionDistribution({ data }: EmotionDistributionProps) {
  const entries = Object.entries(data)

  if (entries.length === 0) {
    return <p className="patient-dash__empty">No emotion data available</p>
  }

  // Sort descending by percentage
  entries.sort((a, b) => b[1] - a[1])

  return (
    <section aria-label="Emotion distribution">
      <h4>Emotion Distribution</h4>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '8px' }}>
        {entries.map(([emotion, pct]) => (
          <span
            key={emotion}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '4px 10px',
              borderRadius: '12px',
              fontSize: '13px',
              fontWeight: 500,
              color: '#fff',
              backgroundColor: getColor(emotion),
            }}
          >
            {emotion} {Math.round(pct * 100)}%
          </span>
        ))}
      </div>
    </section>
  )
}
