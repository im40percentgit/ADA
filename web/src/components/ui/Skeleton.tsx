/**
 * Skeleton — shimmer placeholder for loading states.
 *
 * Four variants cover the common loading shapes:
 *   line   — single text-line placeholder (default height 1em)
 *   block  — rectangular content area (image, chart, card body)
 *   circle — avatar / icon placeholder
 *   card   — full-card skeleton with header row + body lines
 *
 * Shimmer animation uses `--motion-duration-slow` (400 ms) on an infinite
 * linear keyframe. The Phase 13c blanket `prefers-reduced-motion: reduce`
 * override in base.css zeros all animation-duration values, leaving the
 * skeleton as a static muted background — still visually distinct and
 * acceptable without motion.
 *
 * Composed helpers:
 *   SkeletonList — vertical list of N line skeletons
 *   SkeletonCard — card skeleton (circle header + N body lines)
 *
 * All visual values reference CSS custom properties from tokens.css.
 * Inline-style object pattern matches DEC-UI-001/002 (Card, Button).
 *
 * @decision DEC-LOADING-001
 * @title Skeleton shimmer uses CSS keyframe animation via inline style referencing motion tokens
 * @status accepted
 * @rationale Keeps the shimmer definition co-located with the component
 *   rather than in a global stylesheet. Uses var(--motion-duration-slow)
 *   so the animation duration participates in the design-token system.
 *   The prefers-reduced-motion override in base.css (DEC-MOTION-002)
 *   automatically disables it without any per-component media query.
 */

import { type CSSProperties, useEffect } from 'react'

// ---------------------------------------------------------------------------
// Keyframe injection (once per document)
// ---------------------------------------------------------------------------

const KEYFRAME_ID = 'ada-skeleton-shimmer-kf'

function ensureKeyframes() {
  if (typeof document === 'undefined') return
  if (document.getElementById(KEYFRAME_ID)) return
  const style = document.createElement('style')
  style.id = KEYFRAME_ID
  style.textContent = `
@keyframes ada-skeleton-shimmer {
  0%   { background-position: -200% center; }
  100% { background-position:  200% center; }
}
`
  document.head.appendChild(style)
}

// ---------------------------------------------------------------------------
// Base styles
// ---------------------------------------------------------------------------

const baseStyle: CSSProperties = {
  display: 'block',
  borderRadius: 'var(--radius-button)',
  background:
    'linear-gradient(90deg, var(--color-bg-elevated) 25%, var(--color-bg-card) 50%, var(--color-bg-elevated) 75%)',
  backgroundSize: '200% 100%',
  animation: `ada-skeleton-shimmer var(--motion-duration-slow, 400ms) linear infinite`,
}

const variantStyles: Record<string, CSSProperties> = {
  line: {
    height: '1em',
    width: '100%',
    borderRadius: 'var(--radius-button)',
  },
  block: {
    height: '120px',
    width: '100%',
    borderRadius: 'var(--radius-card)',
  },
  circle: {
    height: '40px',
    width: '40px',
    borderRadius: '50%',
    flexShrink: 0,
  },
  card: {
    height: '160px',
    width: '100%',
    borderRadius: 'var(--radius-card)',
  },
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

export interface SkeletonProps {
  variant: 'line' | 'block' | 'circle' | 'card'
  width?: string | number
  height?: string | number
  className?: string
  style?: CSSProperties
  'aria-label'?: string
}

export function Skeleton({
  variant,
  width,
  height,
  className,
  style,
  'aria-label': ariaLabel = 'Loading…',
}: SkeletonProps) {
  useEffect(() => {
    ensureKeyframes()
  }, [])

  const merged: CSSProperties = {
    ...baseStyle,
    ...variantStyles[variant],
    ...(width !== undefined ? { width } : undefined),
    ...(height !== undefined ? { height } : undefined),
    ...style,
  }

  const classes = ['ada-skeleton', `ada-skeleton--${variant}`, className]
    .filter(Boolean)
    .join(' ')

  return (
    <span
      className={classes}
      style={merged}
      role="status"
      aria-label={ariaLabel}
    />
  )
}

// ---------------------------------------------------------------------------
// SkeletonList — vertical stack of N line skeletons
// ---------------------------------------------------------------------------

export interface SkeletonListProps {
  count?: number
  gap?: string
  className?: string
}

export function SkeletonList({ count = 3, gap = 'var(--space-sm)', className }: SkeletonListProps) {
  const listStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap,
  }
  const classes = ['ada-skeleton-list', className].filter(Boolean).join(' ')

  return (
    <div className={classes} style={listStyle}>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} variant="line" width={i % 3 === 2 ? '60%' : '100%'} />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SkeletonCard — circle avatar header + N body lines
// ---------------------------------------------------------------------------

export interface SkeletonCardProps {
  lines?: number
  className?: string
}

export function SkeletonCard({ lines = 2, className }: SkeletonCardProps) {
  const cardStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-sm)',
    padding: 'var(--space-md)',
    background: 'var(--color-bg-card)',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-card)',
  }
  const headerStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-sm)',
  }
  const headerLinesStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-xs, 4px)',
    flex: 1,
  }
  const classes = ['ada-skeleton-card', className].filter(Boolean).join(' ')

  return (
    <div className={classes} style={cardStyle}>
      <div style={headerStyle}>
        <Skeleton variant="circle" />
        <div style={headerLinesStyle}>
          <Skeleton variant="line" width="50%" />
          <Skeleton variant="line" width="30%" />
        </div>
      </div>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} variant="line" width={i === lines - 1 ? '70%' : '100%'} />
      ))}
    </div>
  )
}
