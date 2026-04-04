/**
 * ClockTask.test.tsx — component tests for the SVG clock reading task.
 *
 * ClockTask is a pure presentational component that renders an analog clock
 * with multiple-choice options. Tests verify SVG rendering, option selection,
 * and submit behavior.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ClockTask } from '../../src/components/ClockTask'

describe('ClockTask', () => {
  const defaultProps = {
    hour: 3,
    minute: 15,
    options: ['3:15', '6:30', '9:45', '12:00'],
    onSubmit: vi.fn(),
  }

  it('renders SVG clock', () => {
    render(<ClockTask {...defaultProps} />)
    expect(screen.getByRole('img', { name: 'Analog clock' })).toBeInTheDocument()
  })

  it('renders hour markers', () => {
    render(<ClockTask {...defaultProps} />)
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
  })

  it('renders hour and minute hands', () => {
    render(<ClockTask {...defaultProps} />)
    expect(screen.getByTestId('hour-hand')).toBeInTheDocument()
    expect(screen.getByTestId('minute-hand')).toBeInTheDocument()
  })

  it('renders all option buttons', () => {
    render(<ClockTask {...defaultProps} />)
    for (const option of defaultProps.options) {
      expect(screen.getByRole('button', { name: option })).toBeInTheDocument()
    }
  })

  it('clicking option highlights it', async () => {
    const user = userEvent.setup()
    render(<ClockTask {...defaultProps} />)

    const option = screen.getByRole('button', { name: '3:15' })
    await user.click(option)

    expect(option).toHaveAttribute('aria-pressed', 'true')
  })

  it('clicking a different option changes selection', async () => {
    const user = userEvent.setup()
    render(<ClockTask {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: '3:15' }))
    await user.click(screen.getByRole('button', { name: '6:30' }))

    expect(screen.getByRole('button', { name: '3:15' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '6:30' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('submit fires with selected option', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<ClockTask {...defaultProps} onSubmit={onSubmit} />)

    await user.click(screen.getByRole('button', { name: '9:45' }))
    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onSubmit).toHaveBeenCalledWith('9:45')
  })

  it('submit is disabled when no option is selected', () => {
    render(<ClockTask {...defaultProps} />)
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled()
  })

  it('submit is enabled after selecting an option', async () => {
    const user = userEvent.setup()
    render(<ClockTask {...defaultProps} />)

    await user.click(screen.getByRole('button', { name: '12:00' }))
    expect(screen.getByRole('button', { name: 'Submit' })).not.toBeDisabled()
  })

  it('positions clock hands correctly for given time', () => {
    // hour=3, minute=15 → hourAngle = 3*30 + 15*0.5 = 97.5°, minuteAngle = 15*6 = 90°
    render(<ClockTask {...defaultProps} />)

    const hourHand = screen.getByTestId('hour-hand')
    const minuteHand = screen.getByTestId('minute-hand')

    // Hour hand: angle = 97.5°, length = 50
    // endpoint = (100 + 50*cos(97.5-90), 100 + 50*sin(97.5-90))
    // cos(7.5° in rad) ≈ 0.9914, sin(7.5° in rad) ≈ 0.1305
    // x ≈ 149.57, y ≈ 106.53
    const hx = parseFloat(hourHand.getAttribute('x2')!)
    const hy = parseFloat(hourHand.getAttribute('y2')!)
    expect(hx).toBeCloseTo(149.57, 0)
    expect(hy).toBeCloseTo(106.53, 0)

    // Minute hand: angle = 90°, length = 70
    // endpoint = (100 + 70*cos(0), 100 + 70*sin(0))
    // x = 170, y = 100
    const mx = parseFloat(minuteHand.getAttribute('x2')!)
    const my = parseFloat(minuteHand.getAttribute('y2')!)
    expect(mx).toBeCloseTo(170, 0)
    expect(my).toBeCloseTo(100, 0)
  })
})
