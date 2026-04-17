/**
 * EmptyState.test.tsx — component tests for the EmptyState UI primitive.
 *
 * Verifies:
 * - Required props (icon, title, description) render
 * - All three tone variants apply the correct class
 * - Optional action renders when provided
 * - Optional action is absent when not provided
 * - Semantic structure: title in heading, description in paragraph
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { EmptyState } from '../../../src/components/ui/EmptyState'

describe('EmptyState', () => {
  const baseProps = {
    icon: '💬',
    title: 'No sessions yet',
    description: 'Start your first conversation with Ada.',
  }

  it('renders icon, title, and description', () => {
    render(<EmptyState {...baseProps} />)
    expect(screen.getByText('💬')).toBeTruthy()
    expect(screen.getByText('No sessions yet')).toBeTruthy()
    expect(screen.getByText('Start your first conversation with Ada.')).toBeTruthy()
  })

  it('renders neutral tone by default', () => {
    const { container } = render(<EmptyState {...baseProps} />)
    const el = container.querySelector('.ada-empty-state')
    expect(el?.classList.contains('ada-empty-state--neutral')).toBe(true)
  })

  it('renders warm tone', () => {
    const { container } = render(<EmptyState {...baseProps} tone="warm" />)
    const el = container.querySelector('.ada-empty-state')
    expect(el?.classList.contains('ada-empty-state--warm')).toBe(true)
  })

  it('renders info tone', () => {
    const { container } = render(<EmptyState {...baseProps} tone="info" />)
    const el = container.querySelector('.ada-empty-state')
    expect(el?.classList.contains('ada-empty-state--info')).toBe(true)
  })

  it('renders action when provided', () => {
    render(
      <EmptyState
        {...baseProps}
        action={<button>Start</button>}
      />
    )
    expect(screen.getByRole('button', { name: 'Start' })).toBeTruthy()
  })

  it('does not render action container when action is absent', () => {
    const { container } = render(<EmptyState {...baseProps} />)
    const actionEl = container.querySelector('.ada-empty-state__action')
    expect(actionEl).toBeNull()
  })

  it('renders title as a heading element', () => {
    render(<EmptyState {...baseProps} />)
    // heading role covers h1-h6
    const heading = screen.getByRole('heading', { name: 'No sessions yet' })
    expect(heading).toBeTruthy()
  })

  it('icon is aria-hidden to avoid redundant screen reader announce', () => {
    const { container } = render(<EmptyState {...baseProps} />)
    const iconEl = container.querySelector('.ada-empty-state__icon')
    expect(iconEl?.getAttribute('aria-hidden')).toBe('true')
  })
})
