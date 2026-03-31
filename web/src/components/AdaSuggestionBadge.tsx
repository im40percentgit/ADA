/**
 * @file AdaSuggestionBadge.tsx
 * @description Inline badge rendered on board items that Ada suggested but
 *   a caregiver has not yet approved. Provides Approve and Dismiss actions.
 *   The parent (BoardItem) is responsible for calling the appropriate
 *   board mutation — this component is purely presentational.
 */

interface AdaSuggestionBadgeProps {
  onApprove: () => void
  onDismiss: () => void
}

export function AdaSuggestionBadge({ onApprove, onDismiss }: AdaSuggestionBadgeProps) {
  return (
    <div className="ada-badge">
      <span className="ada-badge__label">Ada suggestion</span>
      <button className="ada-badge__approve" onClick={onApprove} type="button"
              title="Approve this suggestion">Approve</button>
      <button className="ada-badge__dismiss" onClick={onDismiss} type="button"
              title="Dismiss this suggestion">Dismiss</button>
    </div>
  )
}
