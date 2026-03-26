/**
 * @file CircleSelector.tsx
 * @description Dropdown that lets a multi-patient caregiver switch between
 *   their Care Circles. Hidden when the user has only one circle (single-patient
 *   caregivers see no extra UI).
 * @rationale Keeping the selector as a pure controlled component (circles +
 *   selected + onSelect props) makes it trivially testable and keeps selection
 *   state in useCircles rather than scattered across components.
 */

import type { CareCircle } from '../types'

interface CircleSelectorProps {
  circles: CareCircle[]
  selected: CareCircle | null
  onSelect: (circle: CareCircle) => void
}

export function CircleSelector({ circles, selected, onSelect }: CircleSelectorProps) {
  if (circles.length <= 1) return null

  return (
    <div className="circle-selector">
      <label className="circle-selector__label" htmlFor="circle-select">
        Patient:
      </label>
      <select
        id="circle-select"
        className="circle-selector__select"
        value={selected?.id ?? ''}
        onChange={(e) => {
          const circle = circles.find((c) => c.id === e.target.value)
          if (circle) onSelect(circle)
        }}
      >
        {circles.map((c) => (
          <option key={c.id} value={c.id}>
            {c.patient_name}
          </option>
        ))}
      </select>
    </div>
  )
}
