/**
 * PatternGrid.test.tsx — component tests for the visual-spatial memory grid.
 *
 * PatternGrid is a pure presentational component with two phases:
 * display (observe) and recall (reproduce). Tests verify cell rendering,
 * phase transitions, cell toggling, and submit behavior.
 * Uses vi.useFakeTimers() to control the display-to-recall phase transition.
 * Uses fireEvent (not userEvent) for click interactions because userEvent's
 * internal delay mechanism conflicts with fake timers.
 */

import { render, screen, act, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { PatternGrid } from '../../src/components/PatternGrid'

describe('PatternGrid', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  const defaultProps = {
    gridSize: 4,
    highlightedCells: [0, 5, 10, 15],
    displayDuration: 3000,
    onSubmit: vi.fn(),
  }

  it('renders grid with correct number of cells (gridSize * gridSize)', () => {
    render(<PatternGrid {...defaultProps} />)
    const grid = screen.getByTestId('pattern-grid')
    // 4x4 = 16 cells
    expect(grid.children).toHaveLength(16)
  })

  it('renders grid with different grid sizes', () => {
    render(<PatternGrid {...defaultProps} gridSize={3} />)
    const grid = screen.getByTestId('pattern-grid')
    expect(grid.children).toHaveLength(9)
  })

  it('display phase shows highlighted cells', () => {
    render(<PatternGrid {...defaultProps} />)
    // Highlighted cells should have blue background
    const cell0 = screen.getByTestId('cell-0')
    const cell1 = screen.getByTestId('cell-1')

    expect(cell0.style.backgroundColor).toBe('rgb(59, 130, 246)') // #3b82f6
    expect(cell1.style.backgroundColor).toBe('rgb(209, 213, 219)') // #d1d5db (gray)
  })

  it('shows "Memorize the pattern" during display phase', () => {
    render(<PatternGrid {...defaultProps} />)
    expect(screen.getByText('Memorize the pattern')).toBeInTheDocument()
  })

  it('submit button is disabled during display phase', () => {
    render(<PatternGrid {...defaultProps} />)
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled()
  })

  it('cells are not interactive during display phase', () => {
    render(<PatternGrid {...defaultProps} />)
    const cell0 = screen.getByTestId('cell-0')
    // During display phase, cells should not have role="button"
    expect(cell0).not.toHaveAttribute('role', 'button')
  })

  it('after display phase ends, cells become clickable', () => {
    render(<PatternGrid {...defaultProps} />)

    // Advance past display duration inside act() to flush React state updates
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(screen.getByText('Reproduce the pattern')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Submit' })).not.toBeDisabled()

    // Cells should now have role="button"
    const cell0 = screen.getByTestId('cell-0')
    expect(cell0).toHaveAttribute('role', 'button')
  })

  it('clicking a cell toggles selection in recall phase', () => {
    render(<PatternGrid {...defaultProps} />)

    // Transition to recall phase
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    const cell3 = screen.getByTestId('cell-3')

    // Click to select
    fireEvent.click(cell3)
    expect(cell3).toHaveAttribute('aria-pressed', 'true')
    expect(cell3.style.backgroundColor).toBe('rgb(59, 130, 246)')

    // Click again to deselect
    fireEvent.click(cell3)
    expect(cell3).toHaveAttribute('aria-pressed', 'false')
    expect(cell3.style.backgroundColor).toBe('rgb(209, 213, 219)')
  })

  it('submit button calls onSubmit with selected cells', () => {
    const onSubmit = vi.fn()
    render(<PatternGrid {...defaultProps} onSubmit={onSubmit} />)

    // Transition to recall phase
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    // Select cells 0 and 5
    fireEvent.click(screen.getByTestId('cell-0'))
    fireEvent.click(screen.getByTestId('cell-5'))
    fireEvent.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onSubmit).toHaveBeenCalledWith([0, 5])
  })

  it('highlighted cells are no longer shown after transition to recall phase', () => {
    render(<PatternGrid {...defaultProps} />)

    // During display, cell 0 is highlighted
    expect(screen.getByTestId('cell-0').style.backgroundColor).toBe('rgb(59, 130, 246)')

    // Transition to recall phase
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    // After transition, all cells should be gray (no selection yet)
    expect(screen.getByTestId('cell-0').style.backgroundColor).toBe('rgb(209, 213, 219)')
  })
})
