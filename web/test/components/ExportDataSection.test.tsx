/**
 * ExportDataSection.test.tsx — tests for the CSV export card.
 *
 * Verifies that all five download buttons render and trigger window.open()
 * with the correct export URL when clicked. The wellbeing button was added
 * in the recovery port per the mood/wellbeing split decision.
 *
 * @decision DEC-TEST-025
 * @title ExportDataSection tests mock window.open instead of real fetch
 * @status accepted
 * @rationale CSV download uses window.open() which opens a new tab — no
 *   fetch() call is made from JS. Asserting on the window.open() mock
 *   confirms the correct URL is constructed for each export type.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ExportDataSection } from '../../src/components/ExportDataSection'

describe('ExportDataSection', () => {
  beforeEach(() => {
    vi.stubGlobal('open', vi.fn())
  })

  it('renders all five export buttons', () => {
    render(<ExportDataSection patientId="patient-1" />)

    expect(screen.getByRole('button', { name: /assessments csv/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /mood csv/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /wellbeing csv/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /medications csv/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sessions csv/i })).toBeInTheDocument()
  })

  it('renders the Export Data heading', () => {
    render(<ExportDataSection patientId="patient-1" />)
    expect(screen.getByText('Export Data')).toBeInTheDocument()
  })

  it('clicking Assessments CSV triggers window.open with correct URL', async () => {
    const user = userEvent.setup()
    render(<ExportDataSection patientId="patient-1" />)

    await user.click(screen.getByRole('button', { name: /assessments csv/i }))
    expect(window.open).toHaveBeenCalledWith('/api/patients/patient-1/export/assessments')
  })

  it('clicking Mood CSV triggers window.open with correct URL', async () => {
    const user = userEvent.setup()
    render(<ExportDataSection patientId="patient-1" />)

    await user.click(screen.getByRole('button', { name: /mood csv/i }))
    expect(window.open).toHaveBeenCalledWith('/api/patients/patient-1/export/mood')
  })

  it('clicking Wellbeing CSV triggers window.open with correct URL', async () => {
    const user = userEvent.setup()
    render(<ExportDataSection patientId="patient-1" />)

    await user.click(screen.getByRole('button', { name: /wellbeing csv/i }))
    expect(window.open).toHaveBeenCalledWith('/api/patients/patient-1/export/wellbeing')
  })

  it('clicking Medications CSV triggers window.open with correct URL', async () => {
    const user = userEvent.setup()
    render(<ExportDataSection patientId="patient-1" />)

    await user.click(screen.getByRole('button', { name: /medications csv/i }))
    expect(window.open).toHaveBeenCalledWith('/api/patients/patient-1/export/medications')
  })

  it('clicking Sessions CSV triggers window.open with correct URL', async () => {
    const user = userEvent.setup()
    render(<ExportDataSection patientId="patient-1" />)

    await user.click(screen.getByRole('button', { name: /sessions csv/i }))
    expect(window.open).toHaveBeenCalledWith('/api/patients/patient-1/export/sessions')
  })
})
