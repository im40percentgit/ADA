/**
 * Badge — small inline label for status, severity, or category tags.
 *
 * Five semantic variants map to colour pairs chosen for legibility on dark
 * backgrounds. All sizing uses design tokens from `styles/tokens.css`.
 *
 * @decision DEC-UI-003
 * @title Badge colours are hardcoded pairs, not single-token references
 * @status accepted
 * @rationale Each badge variant needs a coordinated bg + text pair that
 *   guarantees contrast. The token layer provides semantic colours but not
 *   every permutation of tinted backgrounds, so the badge defines its own
 *   palette while still using tokens for font-size and spacing.
 */

import type { CSSProperties, ReactNode } from 'react'

export interface BadgeProps {
  variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral'
  children: ReactNode
  className?: string
  /** When true, hides the badge from screen readers (use when decorative next to other text) */
  ariaHidden?: boolean
}

const baseStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 8px',
  borderRadius: '10px',
  fontSize: 'var(--size-xs)',
  fontWeight: 600,
  lineHeight: 1.4,
}

const variantStyles: Record<string, CSSProperties> = {
  success: { background: '#052e16', color: 'var(--color-success)' },
  warning: { background: '#451a03', color: 'var(--color-warning)' },
  danger: { background: '#450a0a', color: 'var(--color-danger)' },
  info: { background: 'var(--color-primary-subtle)', color: 'var(--color-primary-light)' },
  neutral: { background: 'var(--color-bg-elevated)', color: 'var(--color-text-muted)' },
}

export function Badge({ variant, children, className, ariaHidden }: BadgeProps) {
  const merged: CSSProperties = { ...baseStyle, ...variantStyles[variant] }
  const classes = ['ada-badge', `ada-badge--${variant}`, className].filter(Boolean).join(' ')

  return (
    <span className={classes} style={merged} aria-hidden={ariaHidden || undefined}>
      {children}
    </span>
  )
}
