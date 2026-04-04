/**
 * ScreeningTask — routes a CognitiveTaskPresented to the correct task component.
 *
 * Task routing logic:
 *   - task_type === 'text' + task_data.type === 'multiple_choice' → button list
 *   - task_type === 'text' + task_data.type === 'free_text' (or default) → text input
 *   - task_type === 'pattern_grid' → PatternGrid component
 *   - task_type === 'sequence_order' → SequenceOrder component
 *   - task_type === 'clock_reading' → ClockTask component
 *
 * Pure presentation component: receives task data as props, delegates to the
 * appropriate visual component, and calls onSubmit with the user's response.
 *
 * @decision DEC-FRONTEND-061
 * @title ScreeningTask routes by task_type + task_data.type for text subtypes
 * @status accepted
 * @rationale The two-level routing (task_type for modality, task_data.type for
 *   text subtypes) matches the backend CognitiveScreeningAgent's task schema.
 *   Each visual task component (PatternGrid, SequenceOrder, ClockTask) is
 *   already implemented as a standalone pure component, so ScreeningTask
 *   simply adapts their onSubmit signatures to the unified response format.
 */

import { useState } from 'react'
import type { CognitiveTaskPresented } from '../types'
import { PatternGrid } from './PatternGrid'
import { SequenceOrder } from './SequenceOrder'
import { ClockTask } from './ClockTask'

interface ScreeningTaskProps {
  task: CognitiveTaskPresented
  onSubmit: (response: string | Record<string, unknown>) => void
}

function MultipleChoiceTask({
  options,
  onSubmit,
}: {
  options: string[]
  onSubmit: (response: string) => void
}) {
  return (
    <div
      className="screening-task__options"
      role="group"
      aria-label="Answer options"
      style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '400px' }}
    >
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className="screening-task__option"
          onClick={() => onSubmit(option)}
          style={{
            padding: '12px 16px',
            borderRadius: '8px',
            border: '2px solid #d1d5db',
            backgroundColor: '#fff',
            cursor: 'pointer',
            fontWeight: 500,
            fontSize: '1rem',
            textAlign: 'left',
          }}
        >
          {option}
        </button>
      ))}
    </div>
  )
}

function FreeTextTask({ onSubmit }: { onSubmit: (response: string) => void }) {
  const [text, setText] = useState('')

  return (
    <div className="screening-task__free-text" style={{ maxWidth: '400px' }}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type your answer..."
        aria-label="Your answer"
        rows={3}
        style={{
          width: '100%',
          padding: '12px',
          borderRadius: '8px',
          border: '2px solid #d1d5db',
          fontSize: '1rem',
          resize: 'vertical',
          boxSizing: 'border-box',
        }}
      />
      <button
        type="button"
        disabled={text.trim().length === 0}
        onClick={() => onSubmit(text.trim())}
        style={{
          display: 'block',
          margin: '12px auto 0',
          padding: '8px 24px',
          borderRadius: '6px',
          border: 'none',
          backgroundColor: text.trim().length > 0 ? '#3b82f6' : '#9ca3af',
          color: '#fff',
          fontWeight: 600,
          cursor: text.trim().length > 0 ? 'pointer' : 'not-allowed',
        }}
      >
        Submit
      </button>
    </div>
  )
}

export function ScreeningTask({ task, onSubmit }: ScreeningTaskProps) {
  const { task_type, task_data } = task

  if (task_type === 'text') {
    const subtype = task_data.type as string | undefined
    if (subtype === 'multiple_choice' && Array.isArray(task_data.options)) {
      return <MultipleChoiceTask options={task_data.options as string[]} onSubmit={onSubmit} />
    }
    return <FreeTextTask onSubmit={onSubmit} />
  }

  if (task_type === 'pattern_grid') {
    return (
      <PatternGrid
        gridSize={(task_data.grid_size as number) ?? 4}
        highlightedCells={(task_data.highlighted_cells as number[]) ?? []}
        displayDuration={(task_data.display_duration_ms as number) ?? 3000}
        onSubmit={(selectedCells) => onSubmit({ selected_cells: selectedCells })}
      />
    )
  }

  if (task_type === 'sequence_order') {
    return (
      <SequenceOrder
        items={(task_data.items as string[]) ?? []}
        onSubmit={(orderedItems) => onSubmit({ ordered_items: orderedItems })}
      />
    )
  }

  if (task_type === 'clock_reading') {
    return (
      <ClockTask
        hour={(task_data.hour as number) ?? 0}
        minute={(task_data.minute as number) ?? 0}
        options={(task_data.options as string[]) ?? []}
        onSubmit={onSubmit}
      />
    )
  }

  // Fallback for unknown task types
  return (
    <div className="screening-task__unknown" role="alert">
      <p>Unknown task type: {task_type}</p>
    </div>
  )
}
