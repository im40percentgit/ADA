/**
 * PatternGrid — 4xN clickable grid for visual-spatial memory testing.
 *
 * Two phases controlled by useState:
 *   1. Display phase — highlighted cells shown (blue background), grid is
 *      non-interactive, countdown timer visible. Duration from props.
 *   2. Recall phase — all cells gray and clickable. Clicking toggles blue
 *      highlight. Submit button enabled.
 *
 * Pure presentation component: receives task data as props, calls onSubmit
 * with the user's selected cells. No data fetching or API calls.
 *
 * @decision DEC-FRONTEND-050
 * @title PatternGrid uses inline styles with CSS grid for spatial memory task
 * @status accepted
 * @rationale Inline styles keep the component self-contained with no external
 *   CSS dependency. CSS grid with repeat(gridSize, 1fr) adapts to any grid
 *   dimension. The two-phase state machine (display/recall) maps directly to
 *   the cognitive test protocol: observe, then reproduce from memory.
 */

import { useState, useEffect, useCallback, useRef } from 'react'

interface PatternGridProps {
  gridSize: number
  highlightedCells: number[]
  displayDuration: number
  onSubmit: (selectedCells: number[]) => void
}

export function PatternGrid({
  gridSize,
  highlightedCells,
  displayDuration,
  onSubmit,
}: PatternGridProps) {
  const [phase, setPhase] = useState<'display' | 'recall'>('display')
  const [selectedCells, setSelectedCells] = useState<number[]>([])
  const [focusedIndex, setFocusedIndex] = useState(0)
  const cellRefs = useRef<(HTMLDivElement | null)[]>([])
  const prefersReducedMotion = useRef(
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    if (phase !== 'display') return
    // When reduced motion is preferred, don't auto-hide — wait for user action
    if (prefersReducedMotion.current) return
    const timer = setTimeout(() => {
      setPhase('recall')
    }, displayDuration)
    return () => clearTimeout(timer)
  }, [phase, displayDuration])

  const toggleCell = useCallback(
    (index: number) => {
      if (phase !== 'recall') return
      setSelectedCells((prev) =>
        prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index],
      )
    },
    [phase],
  )

  const totalCells = gridSize * gridSize
  const highlightedSet = new Set(highlightedCells)

  const handleCellKeyDown = useCallback(
    (e: React.KeyboardEvent, index: number) => {
      if (phase !== 'recall') return
      const row = Math.floor(index / gridSize)
      const col = index % gridSize
      let nextIndex = index

      switch (e.key) {
        case 'ArrowUp':
          e.preventDefault()
          if (row > 0) nextIndex = (row - 1) * gridSize + col
          break
        case 'ArrowDown':
          e.preventDefault()
          if (row < gridSize - 1) nextIndex = (row + 1) * gridSize + col
          break
        case 'ArrowLeft':
          e.preventDefault()
          if (col > 0) nextIndex = row * gridSize + (col - 1)
          break
        case 'ArrowRight':
          e.preventDefault()
          if (col < gridSize - 1) nextIndex = row * gridSize + (col + 1)
          break
        case 'Enter':
        case ' ':
          e.preventDefault()
          toggleCell(index)
          return
        default:
          return
      }

      if (nextIndex !== index) {
        setFocusedIndex(nextIndex)
        cellRefs.current[nextIndex]?.focus()
      }
    },
    [phase, gridSize, toggleCell],
  )

  const handleReadyClick = useCallback(() => {
    setPhase('recall')
  }, [])

  return (
    <div className="pattern-grid" role="region" aria-label="Pattern memory task">
      <div className="pattern-grid__status" aria-live="polite">
        {phase === 'display' ? 'Memorize the pattern' : 'Reproduce the pattern'}
      </div>

      <div
        className="pattern-grid__grid"
        data-testid="pattern-grid"
        role="grid"
        aria-label="Pattern grid"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${gridSize}, 1fr)`,
          gap: '4px',
          maxWidth: '320px',
          margin: '0 auto',
        }}
      >
        {Array.from({ length: totalCells }, (_, i) => {
          const isHighlighted = phase === 'display' && highlightedSet.has(i)
          const isSelected = phase === 'recall' && selectedCells.includes(i)
          const active = isHighlighted || isSelected
          const cellState = phase === 'display'
            ? (isHighlighted ? 'highlighted' : 'empty')
            : (isSelected ? 'selected' : 'empty')

          return (
            <div
              key={i}
              ref={(el) => { cellRefs.current[i] = el }}
              data-testid={`cell-${i}`}
              role="gridcell"
              tabIndex={phase === 'recall' ? (i === focusedIndex ? 0 : -1) : undefined}
              aria-pressed={phase === 'recall' ? isSelected : undefined}
              aria-label={`Cell ${i + 1}, ${cellState}`}
              onClick={() => toggleCell(i)}
              onKeyDown={(e) => handleCellKeyDown(e, i)}
              style={{
                aspectRatio: '1',
                backgroundColor: active ? '#3b82f6' : '#d1d5db',
                borderRadius: '4px',
                cursor: phase === 'recall' ? 'pointer' : 'default',
                transition: 'background-color 0.15s ease',
              }}
            />
          )
        })}
      </div>

      {phase === 'display' && prefersReducedMotion.current && (
        <button
          className="pattern-grid__ready"
          type="button"
          onClick={handleReadyClick}
          style={{
            display: 'block',
            margin: '16px auto 0',
            padding: '8px 24px',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: '#3b82f6',
            color: '#fff',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          I&apos;m ready
        </button>
      )}

      <button
        className="pattern-grid__submit"
        type="button"
        disabled={phase === 'display'}
        onClick={() => onSubmit(selectedCells)}
        style={{
          display: 'block',
          margin: '16px auto 0',
          padding: '8px 24px',
          borderRadius: '6px',
          border: 'none',
          backgroundColor: phase === 'recall' ? '#3b82f6' : '#9ca3af',
          color: '#fff',
          fontWeight: 600,
          cursor: phase === 'recall' ? 'pointer' : 'not-allowed',
        }}
      >
        Submit
      </button>
    </div>
  )
}
