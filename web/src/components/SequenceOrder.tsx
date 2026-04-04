/**
 * SequenceOrder — tap-to-order component for Trail Making B pattern.
 *
 * Two rows: available items (shuffled) on top, answer sequence (ordered) below.
 * Tapping an available item moves it to the answer row. Tapping an answer item
 * moves it back. Submit button sends the answer sequence.
 *
 * Pure presentation component: receives items as props, calls onSubmit with
 * the user's ordered sequence. No data fetching or API calls.
 *
 * @decision DEC-FRONTEND-051
 * @title SequenceOrder uses two-row tap interface for sequence ordering
 * @status accepted
 * @rationale The two-row layout (available/answer) provides clear visual
 *   feedback about which items have been selected and in what order. Tapping
 *   to move items is more accessible than drag-and-drop for elderly users
 *   and works natively on both desktop and touch devices.
 */

import { useState, useCallback } from 'react'

interface SequenceOrderProps {
  items: string[]
  onSubmit: (orderedItems: string[]) => void
}

export function SequenceOrder({ items, onSubmit }: SequenceOrderProps) {
  const [available, setAvailable] = useState<string[]>([...items])
  const [answer, setAnswer] = useState<string[]>([])

  const selectItem = useCallback((item: string) => {
    setAvailable((prev) => prev.filter((i) => i !== item))
    setAnswer((prev) => [...prev, item])
  }, [])

  const deselectItem = useCallback((item: string) => {
    setAnswer((prev) => prev.filter((i) => i !== item))
    setAvailable((prev) => [...prev, item])
  }, [])

  return (
    <div className="sequence-order" role="region" aria-label="Sequence ordering task">
      <div className="sequence-order__section">
        <p className="sequence-order__label" style={{ fontWeight: 600, marginBottom: '8px' }}>
          Available items
        </p>
        <div
          className="sequence-order__row"
          data-testid="available-row"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', minHeight: '48px' }}
        >
          {available.map((item) => (
            <button
              key={item}
              type="button"
              className="sequence-order__item"
              onClick={() => selectItem(item)}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                border: '2px solid #d1d5db',
                backgroundColor: '#fff',
                cursor: 'pointer',
                fontWeight: 500,
                fontSize: '1rem',
              }}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="sequence-order__section" style={{ marginTop: '16px' }}>
        <p className="sequence-order__label" style={{ fontWeight: 600, marginBottom: '8px' }}>
          Your answer
        </p>
        <div
          className="sequence-order__row"
          data-testid="answer-row"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px',
            minHeight: '48px',
            padding: '8px',
            borderRadius: '6px',
            border: '2px dashed #9ca3af',
            backgroundColor: '#f9fafb',
          }}
        >
          {answer.map((item, index) => (
            <button
              key={item}
              type="button"
              className="sequence-order__item sequence-order__item--selected"
              onClick={() => deselectItem(item)}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                border: '2px solid #3b82f6',
                backgroundColor: '#eff6ff',
                cursor: 'pointer',
                fontWeight: 500,
                fontSize: '1rem',
              }}
            >
              {index + 1}. {item}
            </button>
          ))}
        </div>
      </div>

      <button
        className="sequence-order__submit"
        type="button"
        disabled={answer.length === 0}
        onClick={() => onSubmit(answer)}
        style={{
          display: 'block',
          margin: '16px auto 0',
          padding: '8px 24px',
          borderRadius: '6px',
          border: 'none',
          backgroundColor: answer.length > 0 ? '#3b82f6' : '#9ca3af',
          color: '#fff',
          fontWeight: 600,
          cursor: answer.length > 0 ? 'pointer' : 'not-allowed',
        }}
      >
        Submit
      </button>
    </div>
  )
}
