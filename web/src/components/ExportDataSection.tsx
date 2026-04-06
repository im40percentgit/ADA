/**
 * ExportDataSection — card with CSV download buttons for patient data.
 *
 * Renders five download buttons (Assessments, Mood, Wellbeing, Medications,
 * Sessions) that each open a new browser tab pointing at the backend CSV
 * export endpoint. No client-side data transformation — the backend streams
 * CSV directly with Content-Disposition: attachment.
 *
 * The Wellbeing button was added in the recovery port to match the
 * mood/wellbeing split introduced in T1b (decision C). The /export/mood
 * endpoint returns mood ratings from sessions; /export/wellbeing returns
 * WHO-5 wellbeing scores from the wellbeing_entries table.
 *
 * @decision DEC-FRONTEND-076
 * @title CSV exports use window.open() to backend endpoint
 * @status accepted
 * @rationale The backend generates CSV with correct headers (Content-Type,
 *   Content-Disposition) so the browser handles the download natively.
 *   This avoids loading data into JS memory and re-serializing it, and
 *   works correctly for large datasets that would strain the browser.
 */

import { type CSSProperties } from 'react'
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import { downloadExportCsv } from '../api/client'

export interface ExportDataSectionProps {
  patientId: string
}

const headingStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-h2)',
  fontWeight: 700,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-sm) 0',
}

const descriptionStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-muted)',
  margin: '0 0 var(--space-md) 0',
}

const buttonGridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
  gap: 'var(--space-sm)',
}

const EXPORT_TYPES = [
  { type: 'assessments', label: 'Assessments CSV' },
  { type: 'mood', label: 'Mood CSV' },
  { type: 'wellbeing', label: 'Wellbeing CSV' },
  { type: 'medications', label: 'Medications CSV' },
  { type: 'sessions', label: 'Sessions CSV' },
] as const

export function ExportDataSection({ patientId }: ExportDataSectionProps) {
  return (
    <Card>
      <h2 style={headingStyle}>Export Data</h2>
      <p style={descriptionStyle}>
        Download your data in CSV format for personal records or sharing with healthcare providers.
      </p>
      <div style={buttonGridStyle}>
        {EXPORT_TYPES.map(({ type, label }) => (
          <Button
            key={type}
            variant="secondary"
            onClick={() => downloadExportCsv(patientId, type)}
          >
            {label}
          </Button>
        ))}
      </div>
    </Card>
  )
}
