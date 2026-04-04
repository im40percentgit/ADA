/**
 * ProgressBar — horizontal bar showing a percentage value 0-100.
 *
 * Outer track uses the elevated background; inner fill defaults to the
 * primary colour but accepts a custom `color` prop for contextual uses
 * (e.g. green for adherence, amber for partial). Width transitions
 * smoothly when the value changes.
 *
 * @decision DEC-UI-006
 * @title ProgressBar clamps value 0-100 and accepts optional colour override
 * @status accepted
 * @rationale Clamping prevents visual overflow. A colour prop (rather than
 *   variant names) gives callers precise control without the component
 *   needing to anticipate every use case. The default primary colour keeps
 *   standalone usage consistent with the rest of the design system.
 */

import type { CSSProperties } from 'react'

export interface ProgressBarProps {
  value: number
  color?: string
  className?: string
  /** Accessible label describing what this progress bar measures */
  'aria-label'?: string
}

const outerStyle: CSSProperties = {
  background: 'var(--color-bg-elevated)',
  height: '6px',
  borderRadius: '3px',
  overflow: 'hidden',
}

export function ProgressBar({ value, color, className, 'aria-label': ariaLabel }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value))

  const innerStyle: CSSProperties = {
    width: `${clamped}%`,
    background: color ?? 'var(--color-primary)',
    borderRadius: '3px',
    height: '100%',
    transition: 'width 0.3s',
  }

  const classes = ['ada-progress', className].filter(Boolean).join(' ')

  return (
    <div
      className={classes}
      style={outerStyle}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel}
    >
      <div style={innerStyle} />
    </div>
  )
}
