/**
 * ErrorState — styled error display with optional retry and action slot.
 *
 * Props:
 *   title    — short error heading
 *   message  — human-readable error detail (e.g. err.message)
 *   onRetry  — optional callback; when provided a "Try again" button is rendered
 *   action   — optional ReactNode for additional CTAs (e.g. "Go home" link)
 *
 * Accessibility:
 *   role="status" + aria-label="Error state" so assistive tech announces the
 *   presence of the error without requiring the user to navigate to it.
 *
 * All visual values reference CSS custom properties from tokens.css.
 * Inline-style object pattern matches DEC-UI-001/002 (Card, Button).
 *
 * @decision DEC-ERROR-001
 * @title ErrorState uses role=status + aria-label for a11y announcement
 * @status accepted
 * @rationale role="status" is a live region with aria-live=polite, which
 *   causes screen readers to announce the error when it appears without
 *   interrupting the user mid-sentence (unlike role="alert"/aria-live=assertive).
 *   This is appropriate for async error states that replace loading content.
 */

import type { CSSProperties, ReactNode } from 'react'

export interface ErrorStateProps {
  title: string
  message: string
  onRetry?: () => void
  action?: ReactNode
  className?: string
}

const containerStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  textAlign: 'center',
  padding: 'var(--space-xl, 48px) var(--space-md)',
  gap: 'var(--space-sm)',
}

const iconStyle: CSSProperties = {
  fontSize: '2rem',
  color: 'var(--color-danger)',
  lineHeight: 1,
}

const titleStyle: CSSProperties = {
  margin: 0,
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-h3, 1.125rem)',
  fontWeight: 600,
  color: 'var(--color-text-primary)',
}

const messageStyle: CSSProperties = {
  margin: 0,
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-muted)',
  maxWidth: '40ch',
}

const actionsStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-sm)',
  marginTop: 'var(--space-sm)',
  flexWrap: 'wrap',
  justifyContent: 'center',
}

const retryButtonStyle: CSSProperties = {
  padding: '0 var(--space-md)',
  minHeight: 'var(--touch-target-min)',
  borderRadius: 'var(--radius-button)',
  border: '1px solid var(--color-danger)',
  background: 'transparent',
  color: 'var(--color-danger)',
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  fontWeight: 600,
  cursor: 'pointer',
}

export function ErrorState({
  title,
  message,
  onRetry,
  action,
  className,
}: ErrorStateProps) {
  const classes = ['ada-error-state', className].filter(Boolean).join(' ')
  const hasActions = onRetry != null || action != null

  return (
    <div
      className={classes}
      style={containerStyle}
      role="status"
      aria-label="Error state"
    >
      <span className="ada-error-state__icon" style={iconStyle} aria-hidden="true">
        ⚠
      </span>
      <h3 className="ada-error-state__title" style={titleStyle}>
        {title}
      </h3>
      <p className="ada-error-state__message" style={messageStyle}>
        {message}
      </p>
      {hasActions ? (
        <div className="ada-error-state__actions" style={actionsStyle}>
          {onRetry != null ? (
            <button
              className="ada-error-state__retry"
              style={retryButtonStyle}
              onClick={onRetry}
              type="button"
            >
              Try again
            </button>
          ) : null}
          {action}
        </div>
      ) : null}
    </div>
  )
}
