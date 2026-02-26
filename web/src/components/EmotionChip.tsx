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

  return (
    <div
      className={`emotion-chip ${valenceClass(emotion.valence)}`}
      title={`Valence: ${emotion.valence.toFixed(2)}, Arousal: ${emotion.arousal.toFixed(2)}`}
      role="status"
      aria-label={`Detected emotion: ${emotion.emotion}, confidence ${pct}%`}
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
