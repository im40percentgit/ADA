/**
 * Skeleton.test.tsx — component tests for the Skeleton UI primitive.
 *
 * Verifies:
 * - All four variants render with correct class names
 * - SkeletonList renders N items
 * - SkeletonCard renders header + body lines
 * - Width/height props apply inline styles
 * - role="status" a11y attribute present on all variants
 * - aria-label present on Skeleton root
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Skeleton, SkeletonList, SkeletonCard } from '../../../src/components/ui/Skeleton'

describe('Skeleton', () => {
  it('renders line variant with role=status', () => {
    const { container } = render(<Skeleton variant="line" />)
    const el = container.querySelector('.ada-skeleton--line')
    expect(el).toBeTruthy()
    expect(el?.getAttribute('role')).toBe('status')
  })

  it('renders block variant', () => {
    const { container } = render(<Skeleton variant="block" />)
    const el = container.querySelector('.ada-skeleton--block')
    expect(el).toBeTruthy()
    expect(el?.getAttribute('role')).toBe('status')
  })

  it('renders circle variant', () => {
    const { container } = render(<Skeleton variant="circle" />)
    const el = container.querySelector('.ada-skeleton--circle')
    expect(el).toBeTruthy()
    expect(el?.getAttribute('role')).toBe('status')
  })

  it('renders card variant', () => {
    const { container } = render(<Skeleton variant="card" />)
    const el = container.querySelector('.ada-skeleton--card')
    expect(el).toBeTruthy()
    expect(el?.getAttribute('role')).toBe('status')
  })

  it('applies width as inline style', () => {
    const { container } = render(<Skeleton variant="line" width="60%" />)
    const el = container.querySelector('.ada-skeleton--line') as HTMLElement
    expect(el?.style.width).toBe('60%')
  })

  it('applies height as inline style', () => {
    const { container } = render(<Skeleton variant="block" height="120px" />)
    const el = container.querySelector('.ada-skeleton--block') as HTMLElement
    expect(el?.style.height).toBe('120px')
  })

  it('has aria-label for screen readers', () => {
    const { container } = render(<Skeleton variant="line" />)
    const el = container.querySelector('[role="status"]')
    expect(el?.getAttribute('aria-label')).toBe('Loading…')
  })

  it('accepts custom aria-label', () => {
    const { container } = render(<Skeleton variant="line" aria-label="Loading messages" />)
    const el = container.querySelector('[role="status"]')
    expect(el?.getAttribute('aria-label')).toBe('Loading messages')
  })
})

describe('SkeletonList', () => {
  it('renders N skeleton line items', () => {
    const { container } = render(<SkeletonList count={4} />)
    const items = container.querySelectorAll('.ada-skeleton--line')
    expect(items.length).toBe(4)
  })

  it('defaults to 3 items', () => {
    const { container } = render(<SkeletonList />)
    const items = container.querySelectorAll('.ada-skeleton--line')
    expect(items.length).toBe(3)
  })
})

describe('SkeletonCard', () => {
  it('renders header circle + body lines', () => {
    const { container } = render(<SkeletonCard lines={3} />)
    const circles = container.querySelectorAll('.ada-skeleton--circle')
    // Body lines live directly inside .ada-skeleton-card (not inside the header row)
    const bodyLines = container.querySelectorAll('.ada-skeleton-card > .ada-skeleton--line')
    expect(circles.length).toBeGreaterThanOrEqual(1)
    expect(bodyLines.length).toBe(3)
  })

  it('defaults to 2 body lines', () => {
    const { container } = render(<SkeletonCard />)
    const bodyLines = container.querySelectorAll('.ada-skeleton-card > .ada-skeleton--line')
    expect(bodyLines.length).toBe(2)
  })
})
