/**
 * @file ConfirmDialog.tsx
 * @description A centered confirmation modal with backdrop.
 *   Used for destructive operations (clear board, delete board) that require
 *   explicit user confirmation before proceeding.
 *
 *   - Backdrop click cancels.
 *   - Escape key cancels.
 *   - Confirm button styled with --color-danger to signal destructive action.
 *   - Focus is trapped to the dialog for accessibility.
 *
 * @decision DEC-BOARDS-017
 * @title ConfirmDialog is a standalone modal — no shared modal primitive existed
 * @status accepted
 * @rationale Searched web/src/components/ui/ and web/src/components/ — no
 *   existing modal or dialog primitive was found. Creating a focused component
 *   scoped to the confirmation use case avoids over-engineering a general modal
 *   system for two use sites. If a third use case emerges, promote to ui/.
 */

import { useEffect, useRef } from 'react'

interface ConfirmDialogProps {
  title: string
  message: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null)

  // Focus the confirm button on mount for keyboard accessibility
  useEffect(() => {
    confirmRef.current?.focus()
  }, [])

  // Escape key cancels
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onCancel])

  return (
    <div
      className="confirm-dialog__backdrop"
      onClick={onCancel}
      role="presentation"
    >
      <div
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="confirm-dialog-title" className="confirm-dialog__title">
          {title}
        </h3>
        <p className="confirm-dialog__message">{message}</p>
        <div className="confirm-dialog__actions">
          <button
            className="confirm-dialog__cancel"
            onClick={onCancel}
            type="button"
          >
            Cancel
          </button>
          <button
            ref={confirmRef}
            className="confirm-dialog__confirm"
            onClick={onConfirm}
            type="button"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
