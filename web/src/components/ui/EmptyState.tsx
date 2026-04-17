/**
 * EmptyState — zero-content placeholder with icon, title, description, and optional CTA.
 *
 * Three tone variants express semantic intent without hard-coding colours:
 *   neutral (default) — muted, no specific connotation
 *   warm              — encouraging, used for first-time / onboarding states
 *   info              — informational, used when content is intentionally absent
 *
 * Props:
 *   icon        — emoji string or ReactNode displayed above the title
 *   title       — short heading (rendered as <h3>)
 *   description — supporting sentence(s)
 *   action      — optional ReactNode CTA (Button, link, etc.)
 *   tone        — 'neutral' | 'warm' | 'info'  (default: 'neutral')
 *
 * All visual values reference CSS custom properties from tokens.css.
 * Inline-style object pattern matches DEC-UI-001/002 (Card, Button).
 *
 * @decision DEC-EMPTY-001
 * @title EmptyState uses tone variants via class names + inline token overrides
 * @status accepted
 * @rationale Tone is semantic metadata (neutral/warm/info) rather than
 *   a visual escape hatch, so it maps to class names for predictability.
 *   The per-tone colour is a single token override on the icon element to
 *   avoid three fully duplicated style objects. This keeps the component
 *   light while still being theme-aware.
 */

import type { CSSProperties, ReactNode } from 'react'

export type EmptyStateTone = 'neutral' | 'warm' | 'info'

export interface EmptyStateProps {
  icon: ReactNode
  title: string
  description: string
  action?: ReactNode
  tone?: EmptyStateTone
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
  fontSize: '2.5rem',
  lineHeight: 1,
  marginBottom: 'var(--space-xs, 4px)',
}

// Per-tone icon colour overrides — applied via Object.assign on the icon wrapper
const toneIconColor: Record<EmptyStateTone, string> = {
  neutral: 'var(--color-text-muted)',
  warm: 'var(--color-warning, #f59e0b)',
  info: 'var(--color-primary-light, #818cf8)',
}

const titleStyle: CSSProperties = {
  margin: 0,
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-h3, 1.125rem)',
  fontWeight: 600,
  color: 'var(--color-text-primary)',
}

const descriptionStyle: CSSProperties = {
  margin: 0,
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-muted)',
  maxWidth: '32ch',
}

const actionStyle: CSSProperties = {
  marginTop: 'var(--space-sm)',
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  tone = 'neutral',
  className,
}: EmptyStateProps) {
  const classes = [
    'ada-empty-state',
    `ada-empty-state--${tone}`,
    className,
  ]
    .filter(Boolean)
    .join(' ')

  const resolvedIconStyle: CSSProperties = {
    ...iconStyle,
    color: toneIconColor[tone],
  }

  return (
    <div className={classes} style={containerStyle}>
      <span
        className="ada-empty-state__icon"
        style={resolvedIconStyle}
        aria-hidden="true"
      >
        {icon}
      </span>
      <h3 className="ada-empty-state__title" style={titleStyle}>
        {title}
      </h3>
      <p className="ada-empty-state__description" style={descriptionStyle}>
        {description}
      </p>
      {action ? (
        <div className="ada-empty-state__action" style={actionStyle}>
          {action}
        </div>
      ) : null}
    </div>
  )
}
