/**
 * SequenceOrder.test.tsx — component tests for the tap-to-order sequence task.
 *
 * SequenceOrder is a pure presentational component with two rows: available
 * items and answer items. Tests verify rendering, item movement between rows,
 * and submit behavior.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { SequenceOrder } from '../../src/components/SequenceOrder'

describe('SequenceOrder', () => {
  const defaultProps = {
    items: ['A', '1', 'B', '2', 'C'],
    onSubmit: vi.fn(),
  }

  it('renders all items in the available row', () => {
    render(<SequenceOrder {...defaultProps} />)
    const availableRow = screen.getByTestId('available-row')

    for (const item of defaultProps.items) {
      expect(within(availableRow).getByText(item)).toBeInTheDocument()
    }
  })

  it('answer row is initially empty', () => {
    render(<SequenceOrder {...defaultProps} />)
    const answerRow = screen.getByTestId('answer-row')
    expect(answerRow.children).toHaveLength(0)
  })

  it('tapping an available item moves it to the answer row', async () => {
    const user = userEvent.setup()
    render(<SequenceOrder {...defaultProps} />)

    const availableRow = screen.getByTestId('available-row')
    const answerRow = screen.getByTestId('answer-row')

    await user.click(within(availableRow).getByText('A'))

    // A should now be in answer row (with "1. " prefix)
    expect(within(answerRow).getByText(/A/)).toBeInTheDocument()

    // A should no longer be in available row
    expect(within(availableRow).queryByText('A')).not.toBeInTheDocument()
  })

  it('tapping an answer item moves it back to available row', async () => {
    const user = userEvent.setup()
    render(<SequenceOrder {...defaultProps} />)

    const availableRow = screen.getByTestId('available-row')
    const answerRow = screen.getByTestId('answer-row')

    // Move A to answer
    await user.click(within(availableRow).getByText('A'))

    // Move A back
    await user.click(within(answerRow).getByText(/A/))

    // A should be back in available row
    expect(within(availableRow).getByText('A')).toBeInTheDocument()
    expect(answerRow.children).toHaveLength(0)
  })

  it('submit fires with ordered items', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<SequenceOrder {...defaultProps} onSubmit={onSubmit} />)

    const availableRow = screen.getByTestId('available-row')

    // Select items in order: A, 1, B
    await user.click(within(availableRow).getByText('A'))
    await user.click(within(availableRow).getByText('1'))
    await user.click(within(availableRow).getByText('B'))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onSubmit).toHaveBeenCalledWith(['A', '1', 'B'])
  })

  it('submit is disabled when no items are selected', () => {
    render(<SequenceOrder {...defaultProps} />)
    expect(screen.getByRole('button', { name: 'Submit' })).toBeDisabled()
  })

  it('submit is enabled when at least one item is selected', async () => {
    const user = userEvent.setup()
    render(<SequenceOrder {...defaultProps} />)

    const availableRow = screen.getByTestId('available-row')
    await user.click(within(availableRow).getByText('A'))

    expect(screen.getByRole('button', { name: 'Submit' })).not.toBeDisabled()
  })

  it('preserves order of selected items', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<SequenceOrder {...defaultProps} onSubmit={onSubmit} />)

    const availableRow = screen.getByTestId('available-row')

    // Select in reverse: C, B, A
    await user.click(within(availableRow).getByText('C'))
    await user.click(within(availableRow).getByText('B'))
    await user.click(within(availableRow).getByText('A'))

    await user.click(screen.getByRole('button', { name: 'Submit' }))

    expect(onSubmit).toHaveBeenCalledWith(['C', 'B', 'A'])
  })
})
