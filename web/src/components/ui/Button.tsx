/**
 * Button — design-system button with primary, secondary, and ghost variants.
 *
 * Every visual property references tokens from `styles/tokens.css`. The
 * component supports three sizes (sm / md / lg) via padding and font-size
 * adjustments while always meeting the 44 px minimum touch target.
 *
 * @decision DEC-UI-002
 * @title Button variant styles live in const objects, not CSS classes
 * @status accepted
 * @rationale Inline style objects per variant keep all visual logic
 *   co-located with the component, reference design tokens via var(),
 *   and avoid creating separate CSS files — consistent with the existing
 *   codebase inline-style pattern.
 */

import type { CSSProperties, ReactNode } from 'react'

export interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  onClick?: () => void
  children: ReactNode
  className?: string
  type?: 'button' | 'submit'
}

const baseStyle: CSSProperties = {
  borderRadius: 'var(--radius-button)',
  minHeight: 'var(--touch-target-min)',
  padding: '0 var(--space-md)',
  fontFamily: 'var(--font-body)',
  fontWeight: 600,
  border: 'none',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
}

const variantStyles: Record<string, CSSProperties> = {
  primary: {
    background: 'var(--color-primary)',
    color: '#ffffff',
  },
  secondary: {
    background: 'var(--color-bg-elevated)',
    color: 'var(--color-text-primary)',
  },
  ghost: {
    background: 'transparent',
    color: 'var(--color-text-muted)',
  },
}

const sizeStyles: Record<string, CSSProperties> = {
  sm: { fontSize: 'var(--size-sm)', padding: '0 var(--space-sm)' },
  md: { fontSize: 'var(--size-body)' },
  lg: { fontSize: 'var(--size-h2)', padding: '0 var(--space-lg)' },
}

const disabledStyle: CSSProperties = {
  opacity: 0.5,
  pointerEvents: 'none',
}

export function Button({
  variant = 'primary',
  size = 'md',
  disabled = false,
  onClick,
  children,
  className,
  type = 'button',
}: ButtonProps) {
  const merged: CSSProperties = {
    ...baseStyle,
    ...variantStyles[variant],
    ...sizeStyles[size],
    ...(disabled ? disabledStyle : undefined),
  }

  const classes = ['ada-btn', `ada-btn--${variant}`, className].filter(Boolean).join(' ')

  return (
    <button
      className={classes}
      style={merged}
      onClick={onClick}
      disabled={disabled}
      type={type}
    >
      {children}
    </button>
  )
}
