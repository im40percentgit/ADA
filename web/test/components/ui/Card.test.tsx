/**
 * Card.test.tsx — component tests for the Card UI primitive.
 *
 * Verifies:
 * - Children render inside the card
 * - onClick handler fires when clicked
 * - ada-card--clickable class is applied when onClick is provided
 * - ada-card--clickable class is absent when onClick is not provided
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Card } from '../../../src/components/ui/Card'

describe('Card', () => {
  it('renders children', () => {
    render(<Card>Hello world</Card>)
    expect(screen.getByText('Hello world')).toBeTruthy()
  })

  it('fires onClick when clicked', async () => {
    const handler = vi.fn()
    render(<Card onClick={handler}>Click me</Card>)
    await userEvent.click(screen.getByText('Click me'))
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('applies ada-card--clickable class when onClick is provided', () => {
    const { container } = render(<Card onClick={() => {}}>Clickable</Card>)
    const card = container.querySelector('.ada-card')
    expect(card?.classList.contains('ada-card--clickable')).toBe(true)
  })

  it('does not apply ada-card--clickable class when onClick is absent', () => {
    const { container } = render(<Card>Static</Card>)
    const card = container.querySelector('.ada-card')
    expect(card?.classList.contains('ada-card--clickable')).toBe(false)
  })

  it('merges custom className', () => {
    const { container } = render(<Card className="custom">Styled</Card>)
    const card = container.querySelector('.ada-card')
    expect(card?.classList.contains('custom')).toBe(true)
  })
})
