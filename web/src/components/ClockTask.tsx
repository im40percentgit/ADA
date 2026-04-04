/**
 * ClockTask — SVG analog clock with multiple-choice time reading.
 *
 * Renders an SVG clock face with hour markers (12, 3, 6, 9), hour and minute
 * hands positioned via trigonometry, and a center dot. Multiple-choice buttons
 * below the clock let the user select a time reading. Submit sends the selection.
 *
 * Pure presentation component: receives clock data as props, calls onSubmit
 * with the user's selected answer. No data fetching or API calls.
 *
 * Hand angle formulas (degrees from 12 o'clock, clockwise):
 *   Hour:   (hour % 12) * 30 + minute * 0.5
 *   Minute: minute * 6
 *
 * @decision DEC-FRONTEND-052
 * @title ClockTask uses SVG with trigonometric hand positioning
 * @status accepted
 * @rationale SVG provides resolution-independent rendering of the clock face
 *   with precise trigonometric positioning of hands. The viewBox coordinate
 *   system (0-200) makes angle-to-coordinate math clean. Multiple choice
 *   avoids requiring free-text time input, which would need parsing logic
 *   and is harder for users with motor impairments.
 */

import { useState } from 'react'

interface ClockTaskProps {
  hour: number
  minute: number
  options: string[]
  onSubmit: (selected: string) => void
}

/** Convert angle in degrees (from 12 o'clock) to SVG endpoint coordinates. */
function handEndpoint(angleDeg: number, length: number): { x: number; y: number } {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180
  return {
    x: 100 + length * Math.cos(angleRad),
    y: 100 + length * Math.sin(angleRad),
  }
}

export function ClockTask({ hour, minute, options, onSubmit }: ClockTaskProps) {
  const [selected, setSelected] = useState<string | null>(null)

  const hourAngle = (hour % 12) * 30 + minute * 0.5
  const minuteAngle = minute * 6

  const hourEnd = handEndpoint(hourAngle, 50)
  const minuteEnd = handEndpoint(minuteAngle, 70)

  return (
    <div className="clock-task" role="region" aria-label="Clock reading task">
      <svg
        viewBox="0 0 200 200"
        width="200"
        height="200"
        role="img"
        aria-label={`Analog clock showing ${hour}:${minute.toString().padStart(2, '0')}`}
        style={{ display: 'block', margin: '0 auto' }}
      >
        <title>Analog clock</title>
        <desc>Clock showing {hour}:{minute.toString().padStart(2, '0')}</desc>
        {/* Clock face */}
        <circle cx="100" cy="100" r="95" fill="#fff" stroke="#333" strokeWidth="3" />

        {/* Hour markers */}
        <text x="100" y="25" textAnchor="middle" fontSize="16" fontWeight="bold" fill="#333">
          12
        </text>
        <text x="180" y="105" textAnchor="middle" fontSize="16" fontWeight="bold" fill="#333">
          3
        </text>
        <text x="100" y="190" textAnchor="middle" fontSize="16" fontWeight="bold" fill="#333">
          6
        </text>
        <text x="20" y="105" textAnchor="middle" fontSize="16" fontWeight="bold" fill="#333">
          9
        </text>

        {/* Hour hand */}
        <line
          x1="100"
          y1="100"
          x2={hourEnd.x}
          y2={hourEnd.y}
          stroke="#333"
          strokeWidth="4"
          strokeLinecap="round"
          data-testid="hour-hand"
        />

        {/* Minute hand */}
        <line
          x1="100"
          y1="100"
          x2={minuteEnd.x}
          y2={minuteEnd.y}
          stroke="#333"
          strokeWidth="2"
          strokeLinecap="round"
          data-testid="minute-hand"
        />

        {/* Center dot */}
        <circle cx="100" cy="100" r="4" fill="#333" />
      </svg>

      <div
        className="clock-task__options"
        role="group"
        aria-label="Time options"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '8px',
          marginTop: '16px',
        }}
      >
        {options.map((option) => (
          <button
            key={option}
            type="button"
            className={`clock-task__option${selected === option ? ' clock-task__option--selected' : ''}`}
            onClick={() => setSelected(option)}
            aria-pressed={selected === option}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: `2px solid ${selected === option ? '#3b82f6' : '#d1d5db'}`,
              backgroundColor: selected === option ? '#eff6ff' : '#fff',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '1rem',
            }}
          >
            {option}
          </button>
        ))}
      </div>

      <button
        className="clock-task__submit"
        type="button"
        disabled={selected === null}
        onClick={() => selected && onSubmit(selected)}
        style={{
          display: 'block',
          margin: '16px auto 0',
          padding: '8px 24px',
          borderRadius: '6px',
          border: 'none',
          backgroundColor: selected !== null ? '#3b82f6' : '#9ca3af',
          color: '#fff',
          fontWeight: 600,
          cursor: selected !== null ? 'pointer' : 'not-allowed',
        }}
      >
        Submit
      </button>
    </div>
  )
}
