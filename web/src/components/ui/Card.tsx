/**
 * Card — reusable surface container for grouping related content.
 *
 * Renders a styled <div> with the design-system card surface treatment:
 * card background, border, rounded corners, and standard padding. When
 * an `onClick` handler is provided the card becomes interactive with a
 * pointer cursor and a subtle hover brightness lift.
 *
 * All visual values come from CSS custom properties defined in
 * `styles/tokens.css` so the card automatically inherits theme changes.
 *
 * @decision DEC-UI-001
 * @title Card uses inline styles referencing CSS custom properties
 * @status accepted
 * @rationale Inline style objects that reference `var(--token)` give
 *   zero-CSS-file overhead while keeping every value tied to the shared
 *   design token layer. This matches the existing codebase pattern and
 *   avoids introducing a CSS-in-JS runtime.
 */

import type { CSSProperties, KeyboardEvent, ReactNode } from 'react'

export interface CardProps {
  children: ReactNode
  className?: string
  onClick?: () => void
  style?: CSSProperties
}

const baseStyle: CSSProperties = {
  background: 'var(--color-bg-card)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-card)',
  padding: 'var(--space-md)',
}

const clickableExtra: CSSProperties = {
  cursor: 'pointer',
}

export function Card({ children, className, onClick, style }: CardProps) {
  const isClickable = typeof onClick === 'function'
  const merged: CSSProperties = {
    ...baseStyle,
    ...(isClickable ? clickableExtra : undefined),
    ...style,
  }

  const classes = ['ada-card', isClickable ? 'ada-card--clickable' : '', className]
    .filter(Boolean)
    .join(' ')

  const handleKeyDown = isClickable
    ? (e: KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.()
        }
      }
    : undefined

  return (
    <div
      className={classes}
      style={merged}
      onClick={onClick}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={handleKeyDown}
    >
      {children}
    </div>
  )
}
