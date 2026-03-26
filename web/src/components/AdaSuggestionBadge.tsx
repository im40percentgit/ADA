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
    <span className="ada-suggestion">
      <span className="ada-suggestion__label">Suggested by Ada</span>
      <button
        className="ada-suggestion__approve"
        onClick={onApprove}
        type="button"
        aria-label="Approve Ada suggestion"
      >
        Approve
      </button>
      <button
        className="ada-suggestion__dismiss"
        onClick={onDismiss}
        type="button"
        aria-label="Dismiss Ada suggestion"
      >
        Dismiss
      </button>
    </span>
  )
}
