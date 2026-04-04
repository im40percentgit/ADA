/**
 * EmotionChip — compact display of the current fused emotion state.
 *
 * Shows emoji + emotion label + confidence percentage. Background colour
 * reflects affective valence:
 *   valence > 0.3   → green (positive)
 *   valence < -0.3  → warm red (negative/distressed)
 *   otherwise       → muted blue-grey (neutral)
 *
 * Hidden when no emotion data has been received yet.
 *
 * @decision DEC-FRONTEND-014
 * @title EmotionChip uses valence threshold colouring, not per-emotion colours
 * @status accepted
 * @rationale Colouring by valence (positive/neutral/negative) rather than
 *   by named emotion keeps the colour set to three values and avoids
 *   assigning alarming colours (e.g. red for "angry") that could cause
 *   unintended distress in a therapeutic context. The same visual band
 *   covers the full dimensional emotion space.
 */

import type { WsEmotionUpdate } from '../types'

interface EmotionChipProps {
  emotion: WsEmotionUpdate | null
}

const EMOTION_EMOJI: Record<string, string> = {
  happy: '😊',
  calm: '😌',
  content: '🙂',
  neutral: '😐',
  sad: '😢',
  anxious: '😰',
  fearful: '😨',
  angry: '😠',
  disgusted: '😖',
  surprised: '😲',
}

function emojiFor(emotion: string): string {
  const lower = emotion.toLowerCase()
  return EMOTION_EMOJI[lower] ?? '🫥'
}

function valenceClass(valence: number): string {
  if (valence > 0.3) return 'emotion-chip--positive'
  if (valence < -0.3) return 'emotion-chip--negative'
  return 'emotion-chip--neutral'
}

export function EmotionChip({ emotion }: EmotionChipProps) {
  if (!emotion) return null

  const pct = Math.round(emotion.confidence * 100)

  const badgeBg = emotion.valence > 0.3
    ? '#052e16'
    : emotion.valence < -0.3
      ? '#450a0a'
      : 'var(--color-bg-elevated)'

  const badgeColor = emotion.valence > 0.3
    ? 'var(--color-success)'
    : emotion.valence < -0.3
      ? 'var(--color-danger)'
      : 'var(--color-text-muted)'

  return (
    <div
      className={`emotion-chip ${valenceClass(emotion.valence)}`}
      title={`Valence: ${emotion.valence.toFixed(2)}, Arousal: ${emotion.arousal.toFixed(2)}`}
      role="status"
      aria-label={`Detected emotion: ${emotion.emotion}, confidence ${pct}%`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-xs)',
        padding: '2px 8px',
        borderRadius: '10px',
        fontSize: 'var(--size-xs)',
        fontWeight: 600,
        background: badgeBg,
        color: badgeColor,
        fontFamily: 'var(--font-body)',
      }}
    >
      <span className="emotion-chip__emoji" aria-hidden="true">
        {emojiFor(emotion.emotion)}
      </span>
      <span className="emotion-chip__label">{emotion.emotion}</span>
      <span className="emotion-chip__confidence">{pct}%</span>
      {emotion.modalities.length > 0 && (
        <span className="emotion-chip__modalities" aria-hidden="true">
          {emotion.modalities.map((m) => m[0].toUpperCase()).join('')}
        </span>
      )}
    </div>
  )
}
