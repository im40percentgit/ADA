/**
 * Button.test.tsx — component tests for the Button UI primitive.
 *
 * Verifies:
 * - All three variants render with correct class names
 * - Disabled button does not fire onClick
 * - onClick fires on enabled button
 * - Correct button type attribute
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Button } from '../../../src/components/ui/Button'

describe('Button', () => {
  it('renders primary variant by default', () => {
    const { container } = render(<Button>Save</Button>)
    const btn = container.querySelector('.ada-btn')
    expect(btn?.classList.contains('ada-btn--primary')).toBe(true)
    expect(screen.getByText('Save')).toBeTruthy()
  })

  it('renders secondary variant', () => {
    const { container } = render(<Button variant="secondary">Cancel</Button>)
    const btn = container.querySelector('.ada-btn')
    expect(btn?.classList.contains('ada-btn--secondary')).toBe(true)
  })

  it('renders ghost variant', () => {
    const { container } = render(<Button variant="ghost">Skip</Button>)
    const btn = container.querySelector('.ada-btn')
    expect(btn?.classList.contains('ada-btn--ghost')).toBe(true)
  })

  it('fires onClick when clicked', async () => {
    const handler = vi.fn()
    render(<Button onClick={handler}>Go</Button>)
    await userEvent.click(screen.getByText('Go'))
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('does not fire onClick when disabled', () => {
    const handler = vi.fn()
    render(<Button disabled onClick={handler}>Go</Button>)
    const btn = screen.getByRole('button')
    // Button is disabled natively and has pointer-events: none via inline style
    expect(btn).toHaveProperty('disabled', true)
    expect(btn.style.pointerEvents).toBe('none')
    expect(handler).not.toHaveBeenCalled()
  })

  it('defaults to type="button"', () => {
    render(<Button>Btn</Button>)
    const btn = screen.getByRole('button')
    expect(btn.getAttribute('type')).toBe('button')
  })

  it('accepts type="submit"', () => {
    render(<Button type="submit">Submit</Button>)
    const btn = screen.getByRole('button')
    expect(btn.getAttribute('type')).toBe('submit')
  })
})
